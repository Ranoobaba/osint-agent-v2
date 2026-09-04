#!/usr/bin/env bash
# loop.sh: unattended autoresearch. One headless Claude Code invocation per experiment, cold start,
# state on disk (program.md, results.tsv, LEARNINGS.md, git). Stop with: touch autoresearch/STOP
#
#   ./autoresearch/loop.sh --max-experiments 5        # default cap on OpenRouter spend is $6 (AUTORESEARCH_CAP_USD)
#
# Pattern from ~/autoresearch-harness/fib-moe/night.sh: the agent forgets; the repo doesn't.
set -uo pipefail
cd "$(dirname "$0")/.."
MAX=5
while [[ $# -gt 0 ]]; do case "$1" in --max-experiments) MAX="$2"; shift 2;; *) echo "unknown arg $1" >&2; exit 2;; esac; done
command -v claude >/dev/null || { echo "claude CLI missing"; exit 1; }
rm -f autoresearch/STOP
for i in $(seq 1 "$MAX"); do
  [[ -f autoresearch/STOP ]] && { echo "STOP present, exiting"; break; }
  spent=$(python3 -c 'import json,os;p="autoresearch/spend.json";print(json.load(open(p))["usd"] if os.path.exists(p) else 0)')
  cap="${AUTORESEARCH_CAP_USD:-6}"
  python3 -c "import sys; sys.exit(0 if float('$spent') + 1.35 <= float('$cap') else 1)" || { echo "cap reached (\$$spent of \$$cap)"; break; }
  echo "==> experiment $i ($(date +%H:%M), spent \$$spent)"
  claude -p "You are running one autoresearch experiment in this repo. Read autoresearch/program.md and follow its Procedure exactly: read results.tsv, LEARNINGS.md and git log; pick ONE idea; make the change; run pytest; run the eval; apply the hard rules (keep or revert); append to LEARNINGS.md; commit if kept; then exit. Do not touch files the program forbids." \
    --allowedTools "Bash,Read,Edit,Write,Grep,Glob" --max-turns 60 2>&1 | tail -20
done
echo "loop done"
