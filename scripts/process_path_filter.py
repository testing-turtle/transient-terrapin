from dataclasses import dataclass
import hashlib
import os
import re
import time
from typing import Iterable
import requests
import subprocess
import sys
import yaml

#
# Import the path list specified in FILTER_FILE into a data structure.
# This is a YAML file in the following format:
#
# name: <filter_name>
# files:
#   - <path regex>
#   - <path regex>
#   - <path regex>
# skip-if:
#   all-files-match-any:
#     - <path regex>
#     - <path regex>
#
# The files property is required, the skip-if section is optional.
#


class PathFilter:
    def __init__(self, expression: str):
        self.expression = expression
        self._regex = None

    @property
    def regex(self):
        if self._regex is None:
            self._regex = re.compile(self.expression)
        return self._regex


class SkipIf:
    all_file_match_any: list[PathFilter] | None = None

    def __init__(self, all_file_match_any: list[str] | None = None):
        if all_file_match_any is not None:
            self.all_file_match_any = [PathFilter(e) for e in all_file_match_any]


class Filter:
    name: str
    files: list[PathFilter]
    skip_if: SkipIf | None = None

    def __init__(self, name: str, files: list[str], skip_if: SkipIf | None = None):
        self.name = name
        self.files = [PathFilter(e) for e in files]
        self.skip_if = skip_if

    def is_match_for_file(self, file: str) -> bool:
        """
        Check if the file matches any of the filters
        """
        for path_filter in self.files:
            if path_filter.regex.match(file):
                print(f"Filter {self.name} matched {file} on {path_filter.expression}", flush=True)
                return True
        return False

    def is_match(self, files: Iterable[str]) -> bool:
        match = False
        allFilesMatchAnySkip = (
            self.skip_if is not None and self.skip_if.all_file_match_any is not None
        )
        for file in files:
            if not match:  # only check for a match if we haven't found one yet
                if self.is_match_for_file(file):
                    match = True
            
            if (
                allFilesMatchAnySkip
            ):  # only check for skip if we haven't already had a non-match
                for skip_filter in self.skip_if.all_file_match_any:
                    is_skip_match = skip_filter.regex.match(file)
                    # print(f"Filter {self.name} skip-if match {file} on {skip_filter.expression}: {is_skip_match}", flush=True)
                    if not is_skip_match:
                        print(
                            f"Filter {self.name} skip-if failed to match {file} on {skip_filter.expression}",
                            flush=True,
                        )
                        allFilesMatchAnySkip = False
                        break
        print(f"Filter {self.name} match: {match}, allFilesMatchAnySkip: {allFilesMatchAnySkip}", flush=True)
        result = match and not allFilesMatchAnySkip
        return result

    def calculate_fingerprint(self, files: Iterable[str]) -> str:
        """
        Calculate the fingerprint based on the files that match the filter

        NOTE: to get a stable fingerprint, ensure a consistent order of files
        """

        # iterate the files in the file_list and calculate the sha1 hash
        hash = hashlib.sha1()

        for file in files:
            for path_filter in self.files:
                if path_filter.regex.match(file):
                    # print(f"Adding {file} to hash", flush=True)
                    # Add the filename to the hash
                    hash.update(file.encode("utf-8"))

                    with open(file, "rb") as f:
                        # Read the file in chunks to handle large files
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash.update(chunk)
                    break

        return hash.hexdigest()

def load_git_changes(compare_to: str = "main") -> list[str]:
    print("Attempting to load changes via git...", flush=True)
    # TODO - update to find common ancestor from current commit to compare_to
    # TODO - explore using GH API to get changed files - would remove the need to checkout code
    #        https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", compare_to],
            check=True,
            capture_output=True,
            text=True,
        )
        files = result.stdout.splitlines()
        print(f"Got {len(files)} changed files from git", flush=True)
        return files
    except subprocess.CalledProcessError as e:
        print(
            f"Error getting git changes: {e}\n{e.stdout}\n{e.stderr}", file=sys.stderr, flush=True
        )
        sys.exit(1)


def load_pr_changes() -> list[str]:
    print("Attempting to loading PR changes...", flush=True)
    # GH env vars: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables#default-environment-variables
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token is None:
        print("GITHUB_TOKEN environment variable is not set.", flush=True)
        return None

    github_ref = os.getenv("GITHUB_REF")
    if github_ref is None:
        print("GITHUB_REF environment variable is not set.", flush=True)
        return None

    github_repository = os.getenv("GITHUB_REPOSITORY")
    if github_repository is None:
        print("GITHUB_REPOSITORY environment variable is not set.", flush=True)
        return None

    # parse 'refs/pull/123/merge' to get the PR number
    if not github_ref.startswith("refs/pull/"):
        print(f"Not a PR ref {github_ref}", flush=True)
        return None
    pr_number = github_ref.split("/")[2]

    # API: https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files
    url = f"https://api.github.com/repos/{github_repository}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        # TODO - handle paging!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        files = resp.json()
        file_list = [file["filename"] for file in files]
        print(f"Got {len(file_list)} changed files for PR {pr_number}", flush=True)
        return file_list
    except requests.exceptions.RequestException as e:
        print(f"Error getting PR changes: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def load_filter_file(filter_file: str) -> list[Filter]:
    with open(filter_file, "r") as f:
        filter_data = yaml.safe_load(f)
    if filter_data is None:
        print(f"Filter file {filter_file} is empty.", flush=True)
        sys.exit(1)
    if not isinstance(filter_data, list):
        print(f"Filter file {filter_file} is not a list.", flush=True)
        sys.exit(1)

    filters = []
    for filter_item in filter_data:
        if "name" not in filter_item:
            print(f"Filter file {filter_file} does not contain a name.", flush=True)
            sys.exit(1)
        if "files" not in filter_item:
            print(f"Filter file {filter_file} does not contain a files list.", flush=True)
            sys.exit(1)
        if not isinstance(filter_item["files"], list):
            print(f"Filter file {filter_file} files list is not a list.", flush=True)
            sys.exit(1)
        if len(filter_item["files"]) == 0:
            print(f"Filter file {filter_file} files list is empty.", flush=True)
            sys.exit(1)

        skip_if = None
        if "skip-if" in filter_item:
            if "all-files-match-any" in filter_item["skip-if"]:
                skip_if = SkipIf(filter_item["skip-if"]["all-files-match-any"])

        filter = Filter(
            name=filter_item["name"],
            files=filter_item["files"],
            skip_if=skip_if,
        )
        filters.append(filter)

    return filters

def recursive_file_list(path: str) -> Iterable[str]:
    for root, dirnames, files in os.walk(path, topdown=True):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for file in sorted(files):
            yield os.path.relpath(os.path.join(root, file), path)

def set_github_output(name: str, value: str):
    if os.getenv("GITHUB_OUTPUT") is None:
        print("GITHUB_OUTPUT environment variable is not set.", flush=True)
        sys.exit(1)

    with open(os.getenv("GITHUB_OUTPUT"), "a") as f:
        f.write(f"{name}={value}\n")
    print(f"OUTPUT:{name}={value}", flush=True)

def set_github_env(name: str, value: str):
    if os.getenv("GITHUB_ENV") is None:
        print("GITHUB_ENV environment variable is not set.", flush=True)
        sys.exit(1)

    with open(os.getenv("GITHUB_ENV"), "a") as f:
        f.write(f"{name}={value}\n")

def append_to_step_summary(value: str):
    if os.getenv("GITHUB_STEP_SUMMARY") is None:
        print("GITHUB_STEP_SUMMARY environment variable is not set.", flush=True)
        sys.exit(1)

    with open(os.getenv("GITHUB_STEP_SUMMARY"), "a") as f:
        f.write(f"{value}\n")


if __name__ == "__main__":
    BASE_BRANCH = os.getenv("BASE_BRANCH", "origin/main")

    filter_file = os.getenv("FILTER_FILE")
    if filter_file is None:
        print("FILTER_FILE environment variable is not set.", flush=True)
        sys.exit(1)
    if not os.path.exists(filter_file):
        print(f"Filter file {filter_file} does not exist.", flush=True)
        sys.exit(1)

    filters = load_filter_file(filter_file)
    print(f"Loaded filter file {filter_file} with filters {[f.name for f in filters]}", flush=True)

    file_change_list = load_pr_changes()
    got_changes_from_git = False
    if file_change_list is None:
        file_change_list = load_git_changes(compare_to=BASE_BRANCH)
        got_changes_from_git = True

    append_to_step_summary("## Filter results")

    if len(file_change_list) >10:
        print(f"Changed files (partial list): {file_change_list[0:10]}", flush=True)
        append_to_step_summary(f"Changed files (partial list): {file_change_list[0:10].join(', ')}, ...")
    else:
        append_to_step_summary(f"Changed files: {file_change_list}")
        print(f"Changed files: {file_change_list}", flush=True)

    append_to_step_summary("|Filter|Result|")
    append_to_step_summary("|---|---|")
    for filter in filters:
        start_time = time.time()
        filter_matches = filter.is_match(file_change_list)
        set_github_output(f"filter_{filter.name}", str(filter_matches).lower())
        set_github_env(f"FILTER_{filter.name.upper()}", str(filter_matches).lower())
        append_to_step_summary(f"|{filter.name}|{str(filter.is_match(file_change_list)).lower()}|")

        end_time = time.time()
        duration = end_time - start_time
        print(f"Filter {filter.name} took {duration:.3f} seconds to process", flush=True)
