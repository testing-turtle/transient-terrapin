import fs from 'fs';
import { BlobServiceClient } from '@azure/storage-blob';
import { AzureCliCredential } from '@azure/identity';

function log(message: string) {
	const timestamp = new Date().toISOString();
	// Write message to /tmp/background.log
	fs.appendFileSync('/tmp/background.log', `[${timestamp}] ${message}\n`);
}

log("Lease action - background starting...");

const args = process.argv.slice(2); // Skip the first two args (node and script path)
if (args.length < 1) {
	log("No lease ID provided. Exiting.");
	process.exit(1);
}

const [
	storageAccountName,
	containerName,
	blobPath,
	leaseId,
] = args;

log(`Storage Account: ${storageAccountName}`);
log(`Container Name: ${containerName}`);
log(`Blob Path: ${blobPath}`);
log(`Lease ID: ${leaseId}`);



const credential = new AzureCliCredential();

const blobServiceClient = new BlobServiceClient(`https://${storageAccountName}.blob.core.windows.net`, credential);
const containerClient = blobServiceClient.getContainerClient(containerName);
const blobClient = containerClient.getBlobClient(blobPath);
const leaseClient = blobClient.getBlobLeaseClient(leaseId);


function isMarkerFilePresent(): boolean {
	return fs.existsSync('/tmp/lease-action-marker');
}

function sleep(duration: number): Promise<void> {
	return new Promise(resolve => setTimeout(resolve, duration))
}


async function main() {
	// Start a timer to run every 5 seconds
	// On each tick, check for the marker file
	// If the marker file is present, delete it and exit
	// Otherwise, check whether it's time to renew the lease
	let nextRenewal = Date.now() + 15000;
	while (true) {
		if (isMarkerFilePresent()) {
			log("Marker file found. Deleting marker and exiting background process.");
			fs.rmSync('/tmp/lease-action-marker');
			process.exit(0);
		}
		if (Date.now() < nextRenewal) {
			log("Not time to renew lease yet...");
		} else {
			log(`Renewing lease ID: ${leaseId}`);
			const lease = await leaseClient.renewLease();
			if (lease.errorCode) {
				log(`Failed to renew lease. Error code: ${lease.errorCode}. Exiting.`);
				process.exit(1);
			}
			log(`Lease renewed successfully: lease ID: ${lease.leaseId}`);
			nextRenewal = Date.now() + 15000;
		}
		await sleep(5000)
	}
}

main()