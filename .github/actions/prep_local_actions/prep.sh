#!/bin/bash
set -e

action_names=(
  "check_artifacts"
  "download_artifacts"
  "lease"
  "upload_artifacts"
)

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

for action_name in "${action_names[@]}"; do
  echo -e "###\n### Preparing action: $action_name\n###"
  (cd "$script_dir/../$action_name" && npm install && npm run package)
done
