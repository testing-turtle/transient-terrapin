import fs from 'fs';
import { DefaultArtifactClient } from '@actions/artifact'

console.log("Lease action - post starting...");

// Create the marker file to signal the background process to exit
fs.writeFileSync('/tmp/lease-action-marker', 'exit');
console.log("Created marker file to signal background process to exit.");

const jobName = process.env.GITHUB_JOB || 'unknown';

console.log("Waiting for background process to detect marker and exit...");

let counter = 0;
const counterMax = 20
function processor() {
	if (!fs.existsSync('/tmp/lease-action-marker')) {
		console.log("Marker file deleted, background process should have exited.");
		const artifactClient = new DefaultArtifactClient();
		artifactClient.uploadArtifact(`lease-action-logs-${jobName}`, ['/tmp/background.log'], '/tmp').then(() => {
			console.log("Uploaded background log as artifact 'lease-action-logs'.");
			process.exit(0);
		});
	} else {
		console.log("Marker file still present, waiting...");
		counter++;
		if (counter > counterMax) {
			console.log("Waited too long, exiting anyway.");
			process.exit(1);
		}
		// Check again in 1 second
		setTimeout(() => {
			processor();
		}, 1000);
	}
}

setTimeout(() => {
	processor();
}, 2000);
