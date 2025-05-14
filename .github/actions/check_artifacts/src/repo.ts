import * as github from '@actions/github';
import { exec } from './wrappers.js';



export async function getPRFiles(githubToken: string): Promise<string[] | null> {
	const prNumber = github.context.payload.pull_request?.number;
	if (!prNumber) {
		console.log("No pull request found");
		return null;
	}
	const octokit = github.getOctokit(githubToken);
	const context = github.context;
	const data = await octokit.paginate(octokit.rest.pulls.listFiles, {
		owner: context.repo.owner,
		repo: context.repo.repo,
		pull_number: prNumber,
	});
	return data.map(file => file.filename);
}

export async function getGitChanges(targetBranch: string): Promise<string[] | null> {

	try {
		const { stdout } = await exec(`git diff --name-only ${targetBranch}`);
		const files = stdout.split('\n').filter(file => file.trim() !== '');
		return files;
	} catch (error) {
		console.error(`Error getting git changes: ${error}`);
		return null;
	}
}