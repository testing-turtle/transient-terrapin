import fs from 'fs';


console.log("Lease action - post starting...");

// Create the marker file to signal the background process to exit
fs.writeFileSync('/tmp/lease-action-marker', 'exit');
console.log("Created marker file to signal background process to exit.");


console.log("Waiting for background process to detect marker and exit...");

let counter = 0;
setInterval(() => {
	if (!fs.existsSync('/tmp/lease-action-marker')) {
		console.log("Marker file deleted, background process should have exited.");
		process.exit(0);
	} else {
		console.log("Marker file still present, waiting...");
		counter++;
		if (counter > 20) {
			console.log("Waited too long, exiting anyway.");
			process.exit(1);
		}
	}
}, 1000);


