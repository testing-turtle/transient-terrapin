#!/bin/bash
set -e

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

if [[ $(command -v ncc &> /dev/null; echo $?) == 0 ]]; then
	echo "ncc is already installed"
else
	echo "Installing ncc..."
	npm i -g @vercel/ncc
fi


cd "$script_dir/../.github/actions/check_artifacts"
npm install
ncc build index.js --target es2020

cd "$script_dir/../.github/actions/download_artifacts"
npm install
ncc build index.js

cd "$script_dir/../.github/actions/upload_artifacts"
npm install
ncc build index.js
