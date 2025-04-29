help: ## show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%s\033[0m|%s\n", $$1, $$2}' \
	| column -t -s '|'

install-script-requirements: ## install script requirements
	@pip install -r ./scripts/requirements.txt



compare:
	time GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter.py
	@echo "-------------------"
	time GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter2.py

compare-host: ## Run comparison on host (includes dropping file caches)
	echo 3 | sudo tee /proc/sys/vm/drop_caches
	devcontainerx exec --path . -- bash -c "time FILTER_FILE=${FILTER_FILE} GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter.py"
	devcontainerx exec --path . -- bash -c "time FILTER_FILE=${FILTER_FILE} GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter.py"
	@echo "-------------------"
	 echo 3 | sudo tee /proc/sys/vm/drop_caches
	devcontainerx exec --path . -- bash -c "time FILTER_FILE=${FILTER_FILE} GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter2.py"
	devcontainerx exec --path . -- bash -c "time FILTER_FILE=${FILTER_FILE} GITHUB_OUTPUT=.stuartle.gh-out.txt python ./scripts/process_path_filter2.py"
