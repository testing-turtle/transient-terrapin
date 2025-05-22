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

export interface FileWithHash {
	filename: string;
	hash: string;
}
export async function getFilesWithHashes(ref?: string, root?: string): Promise<FileWithHash[]> {
	const command = `git ls-tree -r --format="%(objectname) %(path)" ${ref ?? "HEAD"} ${root ?? "."}`;
	const { stdout } = await exec(command);
	const filesWithHashes = stdout.split('\n').filter(line => line.trim() !== '').map(
		line => {
			const [hash, filename] = line.split(' ');
			return { filename, hash };
		}
	);
	return filesWithHashes;
}