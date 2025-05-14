import * as core from '@actions/core';
import fs from 'fs';
import path from 'path';

import { exec as cp_exec } from 'child_process';

async function run() {

  const artifactKey = core.getInput('key', { required: true });
  const artifactPaths = core.getMultilineInput('path', { required: true });

  const azureTenantId = core.getInput('azure-tenant-id', { required: true });


  const storageAccountName = core.getInput('storage-account', { required: true });
  const containerName = core.getInput('container', { required: true });

  // Generate a temporary directory to store the artifact zip file
  const tempDir = path.join(process.env.RUNNER_TEMP || '', `artifact-${artifactKey}`);
  fs.mkdirSync(tempDir, { recursive: true });
  const zipPath = path.join(tempDir, 'artifacts.zip');


  function exec(command: string, options?: { env?: NodeJS.ProcessEnv | undefined; }, stdout?: (data: string) => void, stderr?: (data: string) => void) {
    return new Promise<void>((resolve, reject) => {
      const cp = cp_exec(command, options);
      let stdoutContent = '';
      let stderrContent = '';
      cp.on('error', (error) => {
        console.error(`Error executing command: ${command}`);
        reject(error);
      });
      cp.stdout?.on('data', (data) => {
        const content = data.toString();
        if (stdout) {
          stdout(content);
        }
        stdoutContent += content;
      });
      cp.stderr?.on('data', (data) => {
        const content = data.toString();
        if (stderr) {
          stderr(content);
        }
        stderrContent += content;
      });
      cp.on('close', (code) => {
        if (code !== 0) {
          console.error(`Command failed with exit code ${code}: ${command}`);
          reject(new Error(`Command failed with exit code ${code}`));
        } else {
          resolve();
        }
      });
    });
  }

  // Run zip command to create the zip file, passing the artifact paths
  const zipCommand = `zip -r ${zipPath} ${artifactPaths.join(' ')}`;
  console.log("Zipping content...");
  try {
    await exec(zipCommand, undefined, s => console.log(s), s => console.log(s));
    console.log(`Zip file created successfully: ${zipPath}`);
  } catch (error) {
    const execError = error as { message: string };
    console.error(`Error creating zip file: ${execError?.message}`);
    core.setFailed(`Error creating zip file: ${execError?.message}`);
  }

  // Run `azcopy copy`
  const azcopyCommand = `azcopy copy ${zipPath} "https://${storageAccountName}.blob.core.windows.net/${containerName}/${artifactKey}/artifacts.zip" --overwrite=true`;
  console.log("Copying to Azure Storage...");
  let azcopyOutput = '';
  const outputHandler = (data: string) => {
    azcopyOutput += data;
    console.log(data);
  };
  try {
    await exec(azcopyCommand, {
      env: {
        ...process.env,
        AZCOPY_AUTO_LOGIN_TYPE: 'AZCLI',
        AZCOPY_TENANT_ID: azureTenantId,
      },
    }, outputHandler, outputHandler);
    console.log("done!");
  } catch (error) {
    const execError = error as { message: string };
    console.error(`Error copying to Azure Storage: ${execError?.message}`);
    core.setFailed(`Error copying to Azure Storage: ${execError?.message}`);

    // Find lines starting with `Log file is located at: ` and extract the log file path
    const logFilePathMatch = azcopyOutput.match(/Log file is located at: (?<logfile>.*)/);
    const logFilePath = logFilePathMatch?.groups?.logfile;
    if (logFilePath) {
      console.log(JSON.stringify(logFilePath));
      console.log(`\n*****************************************************************\nLog (from ${logFilePath}:`);
      console.log(fs.readFileSync(`${logFilePath}`, {encoding: 'utf8'}));
    }
  }
}

run();