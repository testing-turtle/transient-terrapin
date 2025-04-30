import * as core from '@actions/core';
import * as github from '@actions/github';
import fs from 'fs';
import path from 'path';
import yaml from 'yaml';
import { fileURLToPath } from 'url';
import { DefaultArtifactClient, ArtifactNotFoundError } from '@actions/artifact';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const artifactsFile = core.getInput('artifacts-file');
if (!artifactsFile) {
  core.setFailed('artifacts-file input is required');
}
console.log(`Artifacts file: ${artifactsFile}`);

//
// This action reads a YAML file containing a list of artifacts.
// Each artifact has a filter name and a suffix.
// The filter indicates the repo subtree content that is hashed to identify changes
// The suffix indicates the artifact purpose and allows multiple artifacts for the same subtree
//
// The hashes are loaded from the .hashes directory and need to be generated before the action runs
//
// The action checks if the artifacts exist in the GitHub repository and sets outputs for each artifact
// The outputs are:
// - artifact_fingerprint_<filter_name>: the fingerprint of the artifact. This should be used to fetch/store the artifact
// - artifact_exists_<filter_name>: true if the artifact exists, false otherwise
//


function getHashes() {
  const hashes = {};
  // List files in .hashes directory and load each file
  const dirPath = path.join(__dirname, '../../../.hashes');
  const files = fs.readdirSync(dirPath);
  // console.log("==== hashes ====");
  files.forEach(file => {
    const filePath = path.join(dirPath, file);
    const fileContent = fs.readFileSync(filePath, 'utf8');
    const filterName = path.basename(filePath, ".hash");
    // console.log(`Filter: ${filterName}`);
    // console.log(`Hash: ${fileContent}`);
    hashes[filterName] = fileContent;
  });
  return hashes;
}


async function testArtifactExists(artifactKey) {
  try {
    await artifactClient.getArtifact(artifactKey, { repository: github.context.repo.repo, owner: github.context.repo.owner });
    return true;
  } catch (error) {
    if (error instanceof ArtifactNotFoundError) {
      return false
    }
    throw error;
  }
}

const hashes = getHashes();

console.log("==== hashes ====");
console.log(hashes);

const artifactClient = new DefaultArtifactClient()

// Load the artifacts file and parse the YAML
const artifactsFilePath = path.join(__dirname, '../../../', artifactsFile);
const artifactsFileContent = fs.readFileSync(artifactsFilePath, 'utf8');
const artifacts = yaml.parse(artifactsFileContent);



console.log("==== artifacts ====");
const artifactFingerprintDictionary = {};
const artifactExistsDictionary = {};
for (const artifact of artifacts) {
  const { filter_name, suffix } = artifact;
  const artifactName = `${filter_name}_${suffix}`;
  const fingerprint = `${artifactName}_${hashes[filter_name]}`;
  const artifactExists = await testArtifactExists(fingerprint);
  console.log(`Artifact fingerprint: ${fingerprint} - exists: ${artifactExists}`);
  // Set outputs for the fingerprint for each artifact
  // and whether the artifact exists
  console.log(`Set output artifact_fingerprint_${artifactName}: ${fingerprint}`);
  console.log(`Set output artifact_exists_${artifactName}: ${artifactExists}`);
  core.setOutput(`artifact_fingerprint_${artifactName}`, fingerprint);
  core.setOutput(`artifact_exists_${artifactName}`, artifactExists);
  artifactFingerprintDictionary[artifactName] = fingerprint;
  artifactExistsDictionary[artifactName] = artifactExists;
}

console.log("==== outputs ====");
const artifactFingerprintJson = JSON.stringify(artifactFingerprintDictionary);
const artifactExistsJson = JSON.stringify(artifactExistsDictionary);
console.log("artifact_fingerprint", artifactFingerprintJson);
console.log("artifact_exists", artifactExistsJson);

core.setOutput("fingerprint", artifactFingerprintJson);
core.setOutput("exists", artifactExistsJson);
core.setOutput("test", JSON.stringify({ a: 123, b: 234 }));


// write JSON file with the outputs
const artifactOutputDirectory = path.join(__dirname, '../../../');
const artifactOutputFile = path.join(artifactOutputDirectory, '.artifacts.json');
const result = {};
for (const artifact of artifacts) {
  const { filter_name, suffix } = artifact;
  const artifactName = `${filter_name}_${suffix}`;
  result[artifactName] = {
    fingerprint: artifactFingerprintDictionary[artifactName],
    exists: artifactExistsDictionary[artifactName]
  };
}
fs.writeFileSync(artifactOutputFile, JSON.stringify(result, null, 2), 'utf8');


const artifactResultKey = `artifact_summary_${github.context.repo.owner}_${github.context.repo.repo}_${github.context.runId}`; // TODO - do we need run_attempt?
core.setOutput("artifact_result_key", artifactResultKey);
artifactClient.uploadArtifact(artifactResultKey, [artifactOutputFile], artifactOutputDirectory, { retentionDays: 1 });

