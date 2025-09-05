import fs from 'fs';

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
const leaseId = args[0];

log(`Lease ID: ${leaseId}`);

function isMarkerFilePresent(): boolean {
	return fs.existsSync('/tmp/lease-action-marker');
}

// Start a timer to run every 5 seconds
// On each tick, check for the marker file
// If the marker file is present, delete it and exit
// Otherwise, check whether it's time to renew the lease
let nextRenewal = Date.now() + 15000;
setInterval(() => {
	if (isMarkerFilePresent()) {
		log("Marker file found. Deleting marker and exiting background process.");
		fs.rmSync('/tmp/lease-action-marker');
		process.exit(0);
	}
	if (Date.now() < nextRenewal) {
		log("Not time to renew lease yet...");
		return;
	}
	log(`Renewing lease ID: ${leaseId}`);
	// Actual lease renewal logic goes here ;-)
	nextRenewal = Date.now() + 15000;
}, 5000);


