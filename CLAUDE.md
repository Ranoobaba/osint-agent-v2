# osint-agent-v2

People-intelligence research agent for the Sixtyfour take-home, rebuilt scorer first. Freeform target
in, strict JSON report out, every finding carrying a verbatim source excerpt and page hash.

## Read first
- ~/.claude/plans/eventual-tumbling-babbage.md is the staged plan and the source of truth for schemas,
  the scoring formula, rung presets, and budget arithmetic.
- ~/.gstack/projects/osint-agent-v2/rayyanscomputer-main-design-20260903-152528.md is the design doc.
- PROGRESS.md is the running log: done, in progress, next, blocked.

## Rules that hold in every stage
1. A stage is done only when its rung has run and rows exist in evals/results/ladder.jsonl and
   ladder.md. No mechanism lands without a rung score next to it.
2. Every tool, nudge, gate, and checklist is an env flag read by config.py. Nothing is hard-coded.
3. The model never writes the report. report.py is a pure function of graph + claims + resolution.
4. Claims are admitted by code, per kind. A finding needs an excerpt re-anchored in a source file
   from this run; code stores the verbatim span and the sha256 of the file. Model-supplied excerpt,
   hash, or confidence values are ignored.
5. Identity is decided in code by resolution.py (salvaged from v1 verbatim). The judge runs only in
   the ambiguous band. No model-set boolean is a veto.
6. One Budget object per run, shared by lead and subagents. Data-tool calls are metered;
   record_candidate, record_claim, record_not_found, finish are not.
7. evals/golden.local.jsonl names family members: gitignored forever. runs/ is gitignored.
   examples/ holds public targets only, with recovered private emails hashed before commit.
8. Do not add services. Exactly Exa, Perplexity, Firecrawl paid; GitHub, Gravatar, Wayback,
   whatsmyname free. Cut and not returning: Jina, Maigret, Playwright, PDF, web UI, depth gate,
   speculative dispatch, separate subagent pool.

## Conventions
- Plain language in README, comments, and commits. Never "-" as punctuation. README has an explicit
  Limitations section.
- Commit after each stage with the results row in the message. No Co-Authored-By lines.
- `uv run pytest` must be green before a commit.
- Run a rung: `uv run python evals/ladder.py --rung N`. Score one report:
  `uv run python evals/score.py evals/golden.local.jsonl <id> <report.json> [workspace]`.

## Money
$100 total. Ladder cap $70 (ladder.py enforces it and applies the cut order in the plan), dev $10,
reserve $20 for the reviewer's demo. Development runs use `--dev`.
