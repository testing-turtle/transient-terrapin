import * as github from '@actions/github';
import {exec} from './wrappers.js';



export async function getPRFiles() : Promise<string[] | null> {
	const token = process.env.GITHUB_TOKEN;
	if (!token) {
		console.log("GITHUB_TOKEN not set");
		return null;
	}
	const prNumber = github.context.payload.pull_request?.number;
	if (!prNumber) {
		console.log("No pull request found");
		return null;
	}
	const octokit = github.getOctokit(token);
	const context = github.context;
	const { data } = await octokit.rest.pulls.listFiles({
		owner: context.repo.owner,
		repo: context.repo.repo,
		pull_number: prNumber,
	});
	// TODO pagination!
	return data.map(file => file.filename);
}

export async function getGitChanges(targetBranch: string) : Promise<string[] | null> {

	try {
		const { stdout } = await exec(`git diff --name-only ${targetBranch}`);
		const files = stdout.split('\n').filter(file => file.trim() !== '');
		return files;
	} catch (error) {
		console.error(`Error getting git changes: ${error}`);
		return null;
	}
}