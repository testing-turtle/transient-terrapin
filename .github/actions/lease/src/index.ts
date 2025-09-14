import childProcess from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
// import { openSync } from 'node:fs';
import * as core from '@actions/core';
import { BlobServiceClient } from '@azure/storage-blob';
import { AzureCliCredential } from '@azure/identity';

console.log("Lease action - starting...");

const storageAccountName = core.getInput('storage-account', { required: true });
const containerName = core.getInput('container', { required: true });
const blobPath = core.getInput('blob-path', { required: true });


async function main() {

	// function generateRandomString(length: number): string {
	// 	const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	// 	let result = '';
	// 	const charactersLength = characters.length;
	// 	for (let i = 0; i < length; i++) {
	// 		result += characters.charAt(Math.floor(Math.random() * charactersLength));
	// 	}
	// 	return result;
	// }

	const credential = new AzureCliCredential();

	const blobServiceClient = new BlobServiceClient(`https://${storageAccountName}.blob.core.windows.net`, credential);
	const containerClient = blobServiceClient.getContainerClient(containerName);
	const blobClient = containerClient.getBlobClient(blobPath);

	const exists = await blobClient.exists()
	if (exists) {
		core.info("Blob already exists")
	}else {
		core.info("Blob doesn't exist - creating...")
		await blobClient.getBlockBlobClient().uploadData(Buffer.from("lease file"))
	}

	const leaseClient = blobClient.getBlobLeaseClient();
	const lease = await leaseClient.acquireLease(60);

	if (lease.errorCode) {
		core.error(`Failed to acquire lease. Error code: ${lease.errorCode}`);
		process.exit(1);
	}
	if (!lease.leaseId) {
		core.error(`No lease ID returned`);
		process.exit(1)
	}
	const leaseId = lease.leaseId;
	// const leaseId = generateRandomString(10); // pretend we get a lease ID from somewhere


	// Start a nodejs process that will run after this process exits
	// That process will renew the lease that we got above

	const __dirname = import.meta.dirname;
	console.log("__dirname:", __dirname);

	const scriptPath = path.join(__dirname, 'background.js');
	// const out = openSync('./out.log', 'a');
	// const err = openSync('./out.log', 'a');

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
		// stdio: ['ignore', out, err],
		stdio: 'ignore',
		cwd: __dirname,
	});

	subprocess.unref();
	console.log(`Started background process with PID: ${subprocess.pid} to renew lease ID: ${leaseId}`);

}

main()