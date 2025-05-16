#!/bin/bash
set -e


# TODO - add confirmation!



cache_ids=$(gh api   -H "Accept: application/vnd.github+json"   -H "X-GitHub-Api-Version: 2022-11-28" /repos/testing-turtle/transient-terrapin/actions/caches --paginate | jq .actions_caches[].id)
for id in $cache_ids; do
  echo "Deleting cache with ID: $id"
  gh api -X DELETE -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" /repos/testing-turtle/transient-terrapin/actions/caches/$id
done
