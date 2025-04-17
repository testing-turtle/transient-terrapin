import nanoid
import os
import subprocess
import sys

def checkout_branch(branch_name: str, create: bool = False):

	try:
		if create:
			subprocess.run(["git", "checkout", "-b", branch_name], check=True)
		else:
			subprocess.run(["git", "checkout", branch_name], check=True)
	except subprocess.CalledProcessError as e:
		print(f"Error checking out branch {branch_name}: {e}", file=sys.stderr, flush=True)
		sys.exit(1)

def create_pr_file(id: str):
	pr_file_path = f"dummy_files/pr-{id}.txt"
	if not os.path.exists(os.path.dirname(pr_file_path)):
		os.makedirs(os.path.dirname(pr_file_path))
		
	with open(pr_file_path, "w") as pr_file:
		pr_file.write("This is a test PR file.\n")
		pr_file.write("It contains some test content.\n")

	print(f"Created PR file at {os.path.abspath(pr_file_path)}", flush=True)

def stage_and_commit(message: str):
	subprocess.run(["git", "add", "."])
	subprocess.run(["git", "commit", "-m", message], check=True)

def create_pr(branch_name: str):
	subprocess.run(["gh", "pr", "create", "--title", f"Test PR for {branch_name}", "--body", "This is a test PR."], check=True)


id_suffix = nanoid.generate(size=6)

branch_name = f"test-{id_suffix}"

checkout_branch("main")
print("Checked out main branch", flush=True)

checkout_branch(branch_name, create=True)
print(f"Checked out new branch: {branch_name}", flush=True)

create_pr_file(id_suffix)

stage_and_commit(message=f"Add test file {id_suffix}")
print("Staged and committed changes", flush=True)


create_pr(branch_name)
print(f"Created PR for branch {branch_name}", flush=True)
