#!/usr/bin/env bash
# Open, update or close a GitHub issue that tracks one operational alert.
#
# Item 8 of docs/ops/worklist.md: 45 nightly runs failed unnoticed
# (2026-09-25 to 2026-11-08). A failed run now opens an issue (repo issues
# notify the owner by email and in the GitHub app), a repeat failure comments
# on the same issue instead of opening a new one, and the next success closes
# it. One open issue per alert title, labelled ops-alert.
#
# Usage: alert.sh "<title>" fail|ok "<message>"
# Env:   GH_TOKEN (issues: write), GITHUB_REPOSITORY, RUN_URL (link to the run)
#
# Never put secrets or connection details in the message: this repo and its
# issues are public.
set -euo pipefail

title="${1:?title required}"
state="${2:?state required: fail|ok}"
message="${3:-}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY required}"
run_url="${RUN_URL:-}"
label="ops-alert"

gh label create "$label" --repo "$repo" --color B60205 \
  --description "Automated operational alert (nightly, backup, rank, watchdog)" \
  --force >/dev/null

# Exact-title match among open alert issues (search alone is fuzzy). Listed as
# "number<TAB>title" and matched here, so any title text is safe.
existing=$(gh issue list --repo "$repo" --label "$label" --state open \
  --limit 100 --json number,title --jq '.[] | "\(.number)\t\(.title)"' \
  | awk -F'\t' -v t="$title" '$2 == t { print $1; exit }')

case "$state" in
  fail)
    body="${message}"$'\n\n'"Run: ${run_url}"$'\n\n'"_Opened automatically; closes itself on the next successful run._"
    if [ -n "$existing" ]; then
      gh issue comment "$existing" --repo "$repo" --body "Still failing. ${message}"$'\n\n'"Run: ${run_url}" >/dev/null
      echo "alert: commented on #$existing"
    else
      gh issue create --repo "$repo" --label "$label" --title "$title" --body "$body" >/dev/null
      echo "alert: opened a new issue"
    fi
    ;;
  ok)
    if [ -n "$existing" ]; then
      gh issue close "$existing" --repo "$repo" \
        --comment "Recovered. ${message}"$'\n\n'"Run: ${run_url}" >/dev/null
      echo "alert: closed #$existing"
    else
      echo "alert: nothing open, nothing to do"
    fi
    ;;
  *)
    echo "alert.sh: state must be fail or ok, got '$state'" >&2
    exit 2
    ;;
esac
