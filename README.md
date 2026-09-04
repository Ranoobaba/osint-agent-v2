# osint-agent-v2

A people-intelligence research agent for the Sixtyfour take-home. One line of natural language about
a person goes in; a strict JSON report comes out, where every finding carries the verbatim sentence it
was read from, the sha256 of that page as stored, and the tool that fetched it. Nothing enters the
report that the agent did not read in that run.

It was built scorer first. An evaluation ladder runs nine configurations through one scorer at one
budget, and a mechanism ships only if it moves the number past the measured noise band. The table
lives in evals/results/ladder.md and is copied below as stages land.

## What is different from a normal deep-research agent

- **Claims are admitted by code, not written by the model.** The model proposes a finding with a
  source id and a quoted excerpt. Code re-anchors the quote in the stored page, checks the value is
  inside it, stores the raw span and the page hash, and only then does the claim exist. The report is
  a pure function of the admitted claims. In v1 the report was parsed from the model's last message,
  and tools found facts the report lost.
- **Identity is decided in code.** Every plausible profile goes through record_candidate and a
  deterministic scorer (hard keys email, URL, avatar, handle; soft markers employer, role, location,
  name; resolved needs a score of 0.85 with three independent markers and a runner-up gap). A
  name plus a school never resolves. When two candidates fit and nothing separates them, the report
  says ambiguous, lists both, and attributes nothing. An LLM judge from a different model family runs
  only in the ambiguous band and cannot override a veto.
- **The non-obvious OSINT tactic.** Git commits permanently record the author's email even when the
  GitHub profile hides it, and that data is on no HTML page. github_intel reads push events and recent
  commits to recover real addresses with repo@sha evidence, then pivots into Gravatar (an email's
  hash is a public key into a profile directory) and a whatsmyname sweep across 700 curated sites.
  Rung 2 of the ladder, which has no web search at all, is where this chain is measured.
- **One budget per run**, shared by the lead and any subagents: data-tool calls, dollars (LLM plus
  paid services), seconds. The tightest cap ends the run. Bookkeeping tools are free.
- **Wrong is worse than missing.** The scorer subtracts for contradictions on single-valued fields,
  for any leaked fact about a same-name decoy, and for any claim whose stored span does not contain
  its value. An invented person scores 1.0 only for an empty report.

## Setup

```
uv sync
cp .env.example .env    # OPENROUTER_API_KEY, PERPLEXITY_API_KEY, EXA_API_KEY, FIRECRAWL_API_KEY, GITHUB_TOKEN
uv run pytest
```

## Run

One investigation from the command line:

```
uv run python -m osint2.agent "Michael Jordan, UC Berkeley"
```

Local API:

```
uv run uvicorn osint2.api:app --port 8000
curl -X POST localhost:8000/investigate -H 'content-type: application/json' -d '{"target": "the CTO of Ariglad"}'
curl localhost:8000/jobs/<job_id>              # status, live progress, then the report
curl localhost:8000/jobs/<job_id>/trace        # trace.jsonl
curl localhost:8000/jobs/<job_id>/sources/s003 # the stored page a claim cites
```

Budgets can be raised per request (max_tool_calls, max_usd, max_seconds) but anonymous callers are
clamped to the shipped defaults; an x-api-key matching AGENT_API_KEY lifts the clamp.

Deployed endpoint: https://ranoobaba--osint-agent-v2-web.modal.run (configuration tracks the ladder; final after
rung 9). Deploy with `uv run modal deploy deploy/modal_app.py`.

## The ladder

```
uv run python evals/ladder.py --plan          # presets and the cost table
uv run python evals/ladder.py --rung 2        # run a rung, append rows, re-render the table
uv run python evals/rescore.py                # re-judge every row after a scorer or golden change
```

Rungs: 1 raw Opus with no tools; 2 plus the free OSINT tools; 3 plus input-shape hardening; 4, 5, 6
each add one paid service (Perplexity, Exa, Firecrawl) on a 4-target subset; 7 Perplexity plus Exa;
8 all three on the full set with a call-budget sweep; 9 plus post-resolution deep-dive subagents; D
the shipped configuration through the deployed endpoint.

Targets: the author (32 ground-truth facts, three input shapes: name plus disambiguator, email only,
handle only), a public same-name pair with and without a hard key, "sarah chen, product designer,
ex-figma" (an abstain case: no such person is verifiable), "Michael Jordan, UC Berkeley", "the CTO of
Ariglad", and an invented person with zero search hits. Ground truth lives in
evals/golden.local.jsonl, which is gitignored because it names family members; the schema is in
evals/golden.example.jsonl.

Score per target: recall of ground-truth facts (core 3, deep 2, surprise 1) minus penalties for
wrong claims, with identity as a gate (wrong person is 0). Rung score is the mean over targets. The
noise band is the largest spread between repeated runs of the same configuration on the baseline
target, floored at 0.03.

## Results so far

| rung | configuration | score | identity pass | provenance failures | decoy leaks | cost |
|---|---|---|---|---|---|---|
| v1 | the previous build, its own report re-scored | 0.534 recall | 1/1 | not checked | 0 | |
| 1 | raw Opus, no tools | 0.286 | 2/9 | 0 | 0 | $0.38 |
| 2 | plus GitHub, Gravatar, Wayback, whatsmyname | 0.541 | 5/9 | 0 | 0 | $4.31 |

Rung 1 scores 0.286 only because the two abstain targets reward an empty report; every claim the
model proposed without tools was rejected for lack of a source. The full per-run table is in
evals/results/ladder.md.

## How a finding replays

Take any finding in report.json. Its id names a `claim_admitted` event in trace.jsonl, which carries
the source id, the content hash, and the excerpt. The source id names a file under sources/ (listed in
sources.json). The excerpt is a verbatim substring of that file, and sha256 of the file equals the
content hash. examples/ ships those source files, so every claim there can be checked offline.

## Limitations

- Source URLs are not re-fetched for liveness; provenance is proven against the stored page and its
  hash, which is what the run actually read.
- The ladder measures each mechanism at a cap of 20 data-tool calls per run, not at saturation.
- Tools inside one rung (the four free tools; the input-shape nudges) are measured as a group.
- The single-service rungs run on a 4-target subset chosen by shape; rung 8 on the full set is the
  only check that the subset did not mis-rank a service.
- The resolver is v1's, with one v2 rule: a target that is itself an email address or a bare handle
  resolves on a candidate that matches that key.
- LinkedIn is reachable only through Exa's cached index. Without an Exa key the baseline target,
  whose disambiguator is a LinkedIn URL, stays ambiguous.
- Emails recovered from commit metadata that appear on no public page are hashed before an example
  run is committed; the claim's content hash then refers to the unredacted file.
