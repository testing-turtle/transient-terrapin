import * as core from '@actions/core';
import * as github from '@actions/github';
import fs from 'fs';
import path from 'path';
// import { fileURLToPath } from 'url';
// import { DefaultArtifactClient } from '@actions/artifact';

import { DefaultAzureCredential } from '@azure/identity';
import { BlobServiceClient } from "@azure/storage-blob";

import { loadFilterFile, recursiveFileList } from './filter.js';
import { getWorkflowJobs } from './workflow.js';
import { getGitChanges, getPRFiles } from './repo.js';
import { getRequiredEnvVariable } from './wrappers.js';


const storageAccountName = core.getInput('storage-account', { required: true });
const containerName = core.getInput('container', { required: true });
const filterFile = core.getInput('filter-file', { required: true });
const workflowFile = core.getInput('workflow-file', { required: true });
const githubToken = core.getInput('github-token', { required: true });
const baseRef = core.getInput('base-ref', { required: true });

const stepSummaryFile = getRequiredEnvVariable("GITHUB_STEP_SUMMARY");


console.log("==========================");
console.log("payload", github.context);
console.log("==========================");
console.log("env", process.env);
console.log("==========================");


const azCredential = new DefaultAzureCredential();
const blobClient = new BlobServiceClient(
  `https://${storageAccountName}.blob.core.windows.net`,
  azCredential
);
console.log(`Checking whether container '${containerName}' exists in storage account '${storageAccountName}'`);
const containerClient = blobClient.getContainerClient(containerName)
if (!await containerClient.exists()) {
  console.log(`Container ${containerName} does not exist`);
  process.exit(1);
}
console.log(`Container ${containerName} exists - proceeding with artifact checks`);

async function getChanges() {
  const prChanges = await getPRFiles(githubToken)
  if (prChanges) {
    return prChanges;
  }
  return await getGitChanges(baseRef);
}

function outputChangeFileSummary(changedFiles: string[] | null) {
  fs.appendFileSync(stepSummaryFile, `\n\n## Calculate results\n\n`);
  if (changedFiles) {
    fs.appendFileSync(stepSummaryFile, `Changed files:\n`);
    if (changedFiles.length === 0) {
      fs.appendFileSync(stepSummaryFile, `\nNone\n\n`);
    } else if (changedFiles.length > 10) {
      fs.appendFileSync(stepSummaryFile, `\n- ${changedFiles.slice(0,10).join("\n- ")}\n- ...\n\n`);
    } else {
      fs.appendFileSync(stepSummaryFile, `\n- ${changedFiles.join("\n- ")}\n\n`);
    }
  } else {
    core.warning("Unable to determine changed files - assuming all files may have changed");
    fs.appendFileSync(stepSummaryFile, `Unable to determine changed files - assuming all files may have changed and recomputing hashes\n`);
  }
}

function getCachedHashes() {
  const hashes = new Map<string, string>();
  // List files in .hashes directory and load each file
  // TODO - update to store as JSON in single file
  if (!fs.existsSync(".hashes")) {
    console.log("No .hashes directory found - using empty hash set");
    return hashes;
  }
  const files = fs.readdirSync(".hashes");
  files.forEach(file => {
    const fileContent = fs.readFileSync(`.hashes/${file}`, 'utf8');
    const filterName = path.basename(file, ".hash");
    hashes.set(filterName, fileContent);
  });
  return hashes;
}
function saveCachedHash(jobName: string, hash: string) {
  // Save the hash to the .hashes directory
  const fileName = `.hashes/${jobName}.hash`;
  fs.mkdirSync(".hashes", { recursive: true });
  fs.writeFileSync(fileName, hash);
}

async function testArtifactExists(artifactKey: string) {
  const blobName = `${artifactKey}/artifacts.zip`;
  const exists = await containerClient.getBlobClient(blobName).exists()
  return exists;
}

interface JobInfo {
  hash_changed_files: boolean;
  hash: string;
  artifact_key: string;
  artifact_exists: boolean;
}

async function run() {

  //
  // The goal of this action is to determine which job artifacts already exist
  // for the current state of the repository.
  //
  // To do this, the job reads a filter file that defines filters for each job
  // It then matches a filter set against each job name using the filter name as a regex
  // For each job, it checks the changes for the PR against the filter to see whether there
  // are any changes that match the filter
  //
  // For jobs with changes, it computes the hash of the files in the repository that match
  // the job's filter.
  // For job's without changes, it loads the hash from the .hashes directory which is
  // cached between runs.
  //
  // Once it has all the job hashes, it build a key including the job name and hash
  // and checks if the artifact exists in the Azure blob storage
  //
  // The job outputs both the artifact keys and whether each artifact exists
  //

  console.log(`Loading filter file: ${filterFile}`);
  const filters = loadFilterFile(filterFile);

  console.log(`Loading workflow file: ${workflowFile}`);
  const jobNames = getWorkflowJobs(workflowFile);

  // if we're in a push event (i.e. building after merge), recompute the hashes
  // if it's a workflow_dispatch event, recompute the hashes as we don't know if it's a PR branch or not
  const recomputeHashes = github.context.eventName === "push" || github.context.eventName === "workflow_dispatch";
  const changedFiles = recomputeHashes ? null : await getChanges();

  const cachedHashes = getCachedHashes();
  console.log("==== cached hashes ====");
  console.log(cachedHashes);

  const repoFiles = recursiveFileList(".");

  outputChangeFileSummary(changedFiles);
  fs.appendFileSync(stepSummaryFile, `|Job| Has Changed Files| Hash| Artifact Key| Artifact Exists|\n`);
  fs.appendFileSync(stepSummaryFile, `|---|---|---|---|---|\n`);

  const jobInfoMap: { [key: string]: JobInfo } = {};
  const artifactPrefix = github.context.repo.owner + "/" + github.context.repo.repo;
  for (const jobName of jobNames) {
    let filter = null;
    for (const f of filters) {
      if (f.matchesName(jobName)) {
        filter = f;
        break;
      }
    }
    if (!filter) {
      console.log(`No filter found for job '${jobName}'`);
      continue;
    }
    const hasChangedFiles = changedFiles ? filter.isMatch(changedFiles) : true;
    const hash = (!hasChangedFiles ? cachedHashes.get(jobName) : null) ?? filter.calculateHash(repoFiles);
    saveCachedHash(jobName, hash);
    const artifactKey = `${artifactPrefix}/${jobName}_${hash}`;
    const artifactExists = await testArtifactExists(artifactKey);
    jobInfoMap[jobName] = { hash_changed_files: hasChangedFiles, hash, artifact_key: artifactKey, artifact_exists: artifactExists };
    fs.appendFileSync(stepSummaryFile, `|${jobName}| ${hasChangedFiles}| ${hash}| ${artifactKey}| ${artifactExists}|\n`);
  }

  fs.appendFileSync(
    stepSummaryFile,
    `\n<details>\n<summary>result JSON</summary>\n\n\`\`\`json\n${JSON.stringify(jobInfoMap, null, 2)}\n\n\`\`\`\n</details>\n`);

  core.setOutput("jobs", JSON.stringify(jobInfoMap));
}

run();

