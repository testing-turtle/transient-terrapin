import childProcess from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
// import { openSync } from 'node:fs';

console.log("Lease action - starting...");


function generateRandomString(length: number): string {
	const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
	let result = '';
	const charactersLength = characters.length;
	for (let i = 0; i < length; i++) {
		result += characters.charAt(Math.floor(Math.random() * charactersLength));
	}
	return result;
}

const leaseId = generateRandomString(10); // pretend we get a lease ID from somewhere


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


const subprocess = childProcess.spawn('node', [scriptPath, leaseId], {
	detached: true,
	// stdio: ['ignore', out, err],
	stdio: 'ignore',
	cwd: __dirname,
});

subprocess.unref();
console.log(`Started background process with PID: ${subprocess.pid} to renew lease ID: ${leaseId}`);
