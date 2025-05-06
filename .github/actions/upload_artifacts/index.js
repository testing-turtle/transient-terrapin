import * as core from '@actions/core';
import * as github from '@actions/github';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import { execSync } from 'child_process';


const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const artifactKey = core.getInput('key');
if (!artifactKey) {
  core.setFailed('key input is required');
}
const artifactPaths = core.getMultilineInput('path');
if (!artifactPaths) {
  core.setFailed('path input is required');
}

const azureTenantId = core.getInput('azure-tenant-id', {required: true});


const storageAccountName = core.getInput('storage-account', {required: true});
const containerName = core.getInput('container', {required: true});

// Generate a temporary directory to store the artifact zip file
const tempDir = path.join(process.env.RUNNER_TEMP || '', `artifact-${artifactKey}`);
fs.mkdirSync(tempDir, { recursive: true });
const zipPath = path.join(tempDir, 'artifacts.zip');


// Run zip command to create the zip file, passing the artifact paths
const zipCommand = `zip -r ${zipPath} ${artifactPaths.join(' ')}`;
console.log("Zipping content...");
execSync(zipCommand, (error, stdout, stderr) => {
  if (error) {
    console.error(`Error creating zip file: ${error.message}`);
    core.setFailed(`Error creating zip file: ${error.message}`);
    return;
  }
  if (stderr) {
    console.error(`Error output: ${stderr}`);
    return;
  }
  console.log(`Zip file created successfully: ${zipPath}`);
});


// Run `azcopy copy`
const azcopyLoginCommand = `azcopy copy ${zipPath} "https://${storageAccountName}.blob.core.windows.net/${containerName}/${artifactKey}/artifacts.zip" --overwrite=true`;
console.log("Copying to Azure Storage...");
execSync(azcopyLoginCommand, {
  env: {
    ...process.env,
    AZCOPY_AUTO_LOGIN_TYPE: 'AZCLI',
    AZCOPY_TENANT_ID: azureTenantId,
  },
}, (error, stdout, stderr) => {
  console.log(`stdout: ${stdout}`);
  console.log(`stderr: ${stderr}`);
  if (error) {
    console.error(`Error copying: ${error.message}`);
    core.setFailed(`Error copying: ${error.message}`);
    return;
  }
  console.log(`Successfully copied`);
});


console.log("done!")