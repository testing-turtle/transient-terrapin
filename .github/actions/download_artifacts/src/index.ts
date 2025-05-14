import * as core from '@actions/core';
import fs from 'fs';
import path from 'path';

import { exec as cp_exec } from 'child_process';


async function run() {

  const artifactKey = core.getInput('key');
  if (!artifactKey) {
    core.setFailed('key input is required');
  }
  const artifactPath = core.getInput('path');
  if (!artifactPath) {
    core.setFailed('path input is required');
  }

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

  // Run `azcopy copy`
  const azcopyCommand = `azcopy copy "https://${storageAccountName}.blob.core.windows.net/${containerName}/${artifactKey}/artifacts.zip" ${zipPath}`;
  console.log("Copying from Azure Storage...");
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
  } catch (error) {
    const execError = error as { message: string };
    console.error(`Error copying from Azure Storage: ${execError?.message}`);
    core.setFailed(`Error copying from Azure Storage: ${execError?.message}`);

    // Find lines starting with `Log file is located at: ` and extract the log file path
    const logFilePathMatch = azcopyOutput.match(/Log file is located at: (?<logfile>.*)/);
    const logFilePath = logFilePathMatch?.groups?.logfile;
    if (logFilePath) {
      console.log(JSON.stringify(logFilePath));
      console.log(`\n*****************************************************************\nLog (from ${logFilePath}:`);
      console.log(fs.readFileSync(`${logFilePath}`, {encoding: 'utf8'}));
    }

    process.exit(1);
  }

  // Run unzip command to extract the zip file to the specified path
  const zipCommand = `unzip ${zipPath} -d ${artifactPath}`;
  console.log("Unzipping content...");
  try {
    await exec(zipCommand, undefined, s => console.log(s), s => console.log(s));
    console.log(`Zip file created successfully: ${zipPath}`);
  } catch (error) {
    const execError = error as { message: string };
    console.error(`Error creating zip file: ${execError?.message}`);
    core.setFailed(`Error creating zip file: ${execError?.message}`);
  }


  console.log("done!")
}

run();