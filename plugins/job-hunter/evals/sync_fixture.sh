#!/bin/sh
# Copies _fixture/job-search into every case. add_dirs must live inside the case, so each case
# carries its own copy; edit _fixture/ and rerun this instead of editing the copies.
cd "$(dirname "$0")"
for c in */prompt.md; do
  d=$(dirname "$c"); rm -rf "$d/job-search"; cp -R _fixture/job-search "$d/job-search"
done
echo "fixture synced to $(ls -d */prompt.md | wc -l | tr -d ' ') cases"
