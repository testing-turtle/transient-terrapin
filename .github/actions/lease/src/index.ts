import childProcess from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import * as core from '@actions/core';
import { BlobLeaseClient, BlobServiceClient } from '@azure/storage-blob';
import { AzureCliCredential } from '@azure/identity';

import { sleep } from './utils.js'

console.log("Lease action - starting...");

const storageAccountName = core.getInput('storage-account', { required: true });
const containerName = core.getInput('container', { required: true });
const blobPath = core.getInput('blob-path', { required: true });

const credential = new AzureCliCredential();

const blobServiceClient = new BlobServiceClient(`https://${storageAccountName}.blob.core.windows.net`, credential);
const containerClient = blobServiceClient.getContainerClient(containerName);
const blobClient = containerClient.getBlobClient(blobPath);

async function getLease(leaseClient: BlobLeaseClient) {
	while (true) { // TODO - limit the amount of time to wait for a lease
		core.info("Attempting to acquire lease...")
		try {
			const lease =  await leaseClient.acquireLease(60);
			core.info("Lease acquired")
			return lease;
		} catch (error: any) {
			if ("code" in error && error.code == "LeaseAlreadyPresent") {
				// lease is already acquired - wait and retry
				core.info("Lease already present - sleeping...")
				await sleep(20000)
			} else {
				core.info(`Failed to acquire lease: ${error}`);
				throw error;
			}
		}
	}
}

async function main() {

	const exists = await blobClient.exists()
	if (exists) {
		core.info("Blob already exists")
	} else {
		core.info("Blob doesn't exist - creating...")
		await blobClient.getBlockBlobClient().uploadData(Buffer.from("lease file"))
	}

	const leaseClient = blobClient.getBlobLeaseClient();
	const lease = await getLease(leaseClient);

	if (lease.errorCode) {
		core.error(`Failed to acquire lease. Error code: ${lease.errorCode}`);
		process.exit(1);
	}
	if (!lease.leaseId) {
		core.error(`No lease ID returned`);
		process.exit(1)
	}
	const leaseId = lease.leaseId;

	// Start a nodejs process that will run after this process exits
	// That process will renew the lease that we got above
	const __dirname = import.meta.dirname;
	const scriptPath = path.join(__dirname, 'background.js');

	// Ensure that there is no leftover marker file from a previous run
	fs.rmSync('/tmp/lease-action-marker', { force: true });
	// Clear the background log file
	fs.rmSync('/tmp/background.log', { force: true });

	const args = [
		scriptPath,
		storageAccountName,
		containerName,
		blobPath,
		leaseId,
	];
	const subprocess = childProcess.spawn('node', args, {
		detached: true,
		stdio: 'ignore',
		cwd: __dirname,
	});

	subprocess.unref();
	console.log(`Started background process with PID: ${subprocess.pid} to renew lease ID: ${leaseId}`);
}

main()