import fs from 'fs';
import yaml from 'yaml';

export function getWorkflowJobs(workfileFilename: string) {
	const workflowFile = fs.readFileSync(workfileFilename, 'utf8');
	const workflow = yaml.parse(workflowFile);
	if (!workflow) {
		throw new Error(`Failed to parse workflow file: ${workfileFilename}`);
	}
	if (!workflow.jobs) {
		throw new Error(`No jobs found in workflow file: ${workfileFilename}`);
	}
	// get keys of jobs map
	const jobKeys = Object.keys(workflow.jobs);
	return jobKeys;
}