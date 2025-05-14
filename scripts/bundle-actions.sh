#!/bin/bash
set -e

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [[ $(command -v ncc &> /dev/null; echo $?) == 0 ]]; then
	echo "ncc is already installed"
else
	echo "Installing ncc..."
	npm i -g @vercel/ncc
fi

if [[ $(command -v typescript &> /dev/null; echo $?) == 0 ]]; then
	echo "typescript is already installed"
else
	echo "Installing typescript..."
	npm i -g typescript
fi


cd "$script_dir/../.github/actions/check_artifacts"
npm install
npm run package

cd "$script_dir/../.github/actions/download_artifacts"
npm install
npm run package

cd "$script_dir/../.github/actions/upload_artifacts"
npm install
npm run package
