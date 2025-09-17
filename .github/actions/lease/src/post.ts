import fs from 'fs';
import { DefaultArtifactClient } from '@actions/artifact'
import { sleep } from './utils.js';

console.log("Lease action - post starting...");

// Create the marker file to signal the background process to exit
fs.writeFileSync('/tmp/lease-action-marker', 'exit');
console.log("Created marker file to signal background process to exit.");

const jobName = process.env.GITHUB_JOB || 'unknown';

function uploadBackgroundLog() {
	const artifactClient = new DefaultArtifactClient();
	artifactClient.uploadArtifact(`lease-action-logs-${jobName}`, ['/tmp/background.log'], '/tmp').then(() => {
		console.log("Uploaded background log as artifact 'lease-action-logs'.");
		process.exit(0);
	});
}

async function main() {
	console.log("Waiting for background process to detect marker and exit...");

	const counterMax = 20
	for (let counter = 0; counter < counterMax; counter++) {
		if (!fs.existsSync('/tmp/lease-action-marker')) {
			console.log("Marker file deleted, background process should have exited.");
			uploadBackgroundLog();
			break;
		}
		console.log("Marker file still present, waiting...");
		counter++;
		if (counter > counterMax) {
			console.log("Waited too long, exiting anyway.");
			uploadBackgroundLog();
			process.exit(1);
		}
		await sleep(2000);
	}
}
main()