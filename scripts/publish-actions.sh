#!/bin/bash
set -e

action_names=(
  "check_artifacts"
  "download_artifacts"
  "lease"
  "upload_artifacts"
)

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function get_action_version() {
  local action_name="$1"
  local version
  version=$(node -p "require('$script_dir/../.github/actions/$action_name/package.json').version")
  echo "$version"
}
function get_major_version() {
  local version="$1"
  IFS='.' read -r major _ <<< "$version"
  echo "$major"
}
function git_tag_exists() {
  local tag="$1"
  if git rev-parse "$tag" >/dev/null 2>&1; then
	return 0
  else
	return 1
  fi
}
function git_dirty() {
  if [[ -n $(git status --porcelain) ]]; then
	return 0
  else
	return 1
  fi
}
function set_repo_content_for_action() {
  local action_name="$1"
  local version="$2"
  
  # run package to compile action
  (cd "$script_dir/../.github/actions/$action_name" && npm install && npm run package)

  # Copy action files to root
  cp "$script_dir/../.github/actions/$action_name/action.yml" .
  cp -r "$script_dir/../.github/actions/$action_name/dist" .

  # Clear other files from the root to leave action.yml and dist only
  find . -maxdepth 1 ! -name '.' ! -name 'action.yml' ! -name 'dist' ! -name '.git' -exec rm -rf {} > /dev/null +

  # Commit changes

  git add -A > /dev/null
  git commit -m "Publish action $action_name version $version" > /dev/null
}

function publish_action() {
  local action_name="$1"
  echo ""
  echo -e "###\n### Preparing to publish action: $action_name\n###"
  
  local version
  local major_version
  version=$(get_action_version "$action_name")
  major_version=$(get_major_version "$version")
  echo "### Action version: $version (major: $major_version)"

  action_tag="$action_name-v$version"
  action_major_tag="$action_name-v$major_version"

  if git_tag_exists "$action_tag"; then
	echo "### Git tag $action_tag already exists. Skipping publish for $action_name."
	return
  fi

  echo "### Creating git tag $action_tag for action $action_name"

  # Save current git branch to return later
  current_branch=$(git branch --show-current)
  git checkout -B "publish-$action_name"

  # Set repo content to just compiled action files, commit, tag, and push
  set_repo_content_for_action "$action_name" "$version"
  git tag "$action_tag"
  git push origin "$action_tag"
  # force update major version tag to point to latest
  git tag -f "$action_major_tag"
  git push -f origin "$action_major_tag"

  # Restore previous git branch so that the next publish starts from the correct place
  git checkout "$current_branch"
}


if git_dirty; then
  echo "Git working directory is dirty. Please commit or stash your changes before publishing."
  exit 1
fi
for action_name in "${action_names[@]}"; do
  publish_action "$action_name"
done

