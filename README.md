# osint-agent-v2

A people-intelligence research agent that takes one line of natural language about a person and
returns structured findings, each with a verbatim source excerpt and a page hash so anyone can
replay it back to the page. Built scorer first: an evaluation ladder scores nine configurations
with one scorer at one budget, and a mechanism ships only if it moves the number.

Status: Stage 0 of 10. See PROGRESS.md and evals/results/ladder.md.

## Setup

```
uv sync
cp .env.example .env   # fill in the keys
uv run pytest
```

## Score a report

```
uv run python evals/score.py evals/golden.local.jsonl <golden id> <report.json> [workspace dir]
```

## Limitations

Filled in as the stages land. Known from the design: source URLs are not re-fetched for liveness
(provenance is proven against the stored excerpt and hash); the ladder measures mechanisms at a
20-call cap, not at saturation; tools inside one rung are ablated as a group.
