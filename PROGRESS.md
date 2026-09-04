# Progress

## Done
- Stage 0 (2026-09-03): folder, uv project on Python 3.12, salvage of resolution.py, trace.py,
  workspace.py, graph.py, schema.py and their tests from v1; evals/score.py with the full formula
  (identity branches, recall, contradiction / decoy / provenance penalties); evals/v1_adapter.py;
  evals/results.py (ladder.jsonl, ladder.md, spend.json). Calibration row rung=v1-calib recorded:
  the new scorer reproduces v1's number on v1's saved report, net 0.534, core 78 / deep 38 /
  surprise 0, identity PASS, provenance not checked (v1 findings carry no excerpt).

- Stage 1 (2026-09-03): runtime core (config with env flags, shared Budget with reserve/settle, OpenRouter
  client with caching, EvidenceStore with excerpt re-anchoring and per-kind admission, tool registry that
  stores every data result as a hashed source, record_candidate / record_claim / record_not_found / finish,
  anchors, report builder with code-owned confidence, lead loop with pruning and dry-step stopping), the
  ladder runner (presets, repeats, concurrency 3, spend cap and cut order), 41 tests. Golden entries 2, 3
  (own facts under email-only and handle-only inputs), 6 to 9 (public targets, researched with URLs).
  Rung 1 recorded: 9 runs, 7 targets, score 0.286, $0.38. Every resolvable target scores 0 (no source to
  cite, all claims rejected); the two abstain targets score 1.0. Candidates from memory are rejected too.
  Surprise from research: "sarah chen, product designer, ex-figma" has no verifiable real person behind it
  (every hit is a template or demo page), so it is now an abstain target, expected unresolved.

- Stage 2 (2026-09-03): free tools ported (github_intel, gravatar, wayback, whatsmyname), judge wired in
  the ambiguous band, PRUNE_STEPS flag (off: append-only window, 90 percent prompt-cache hits, LLM cost
  per run 1.38 to 0.56 dollars). Admission grows a quoted span to reach a value within 400 chars and
  names the line to quote on rejection. Rung 2 recorded: 9 runs, score 0.474 vs rung 1 0.286 (+0.188,
  band 0.030, moved), 4.31 dollars, 0 provenance failures, 0 decoy leaks, identity 5/9. Email-only
  resolved through the commit-email chain; Ariglad CTO resolved at recall 0.71 on free tools; baseline
  stays ambiguous (its LinkedIn key is unreachable without a paid fetch). Michael Jordan's one penalty
  was a golden gap (Inria's title rendered as Senior Researcher); golden widened, rows rescored.

- Stage 3 (2026-09-04): input-shape hardening. Two code fixes (a bare token is a handle; a target that
  is itself an email or handle resolves on a candidate matching that key) and one flag
  (NUDGE_INPUT_SHAPE: a first-move line per target type in the recitation). Rung 3 recorded: 7 runs,
  score 0.555 vs rung 2 0.541, +0.014, band 0.030, did NOT move as a group. handle_only went 0.147 to
  0.362 (the resolver rule); michael_jordan dipped 0.471 to 0.353 (noise, same tools). Verdict: the
  resolver rule is a correctness fix and stays; the nudge flag did not prove itself. It stays on in
  rungs 4 to 9 because rung 4 already ran with it, and it can be ablated at the end for about 3.5
  dollars if money remains. 3.45 dollars.

- Stage 4 (2026-09-04): Perplexity search behind TOOLS=perplexity, charged 0.005 per call. Rung 4
  recorded on the 3 available subset targets: score 0.788 vs rung 3 on the same targets, +0.233, moved.
  The baseline now RESOLVES (net 0.483, recall 0.48) because search corroborates employer and location
  across domains; michael_jordan 0.882; invented 1.0. 0 provenance failures, 0 decoy leaks. 2.12 dollars.

- Deploy plumbing verified 2026-09-04: https://ranoobaba--osint-agent-v2-web.modal.run (Modal spawn/poll,
  Volume-backed workspaces, GET /jobs/{id}/trace and /sources/{id}). Shipped configuration is not final
  until rungs 8 and 9 run.

- Stage 6 (2026-09-04): Firecrawl fetch behind TOOLS=firecrawl (FIRECRAWL_API_KEY was present on a
  line with a leading space; normalized). Rung 6 recorded on the 3 available subset targets: score 0.382
  vs rung 3 on the same targets 0.494, did NOT move (Firecrawl alone adds nothing the free tools and
  the walled hosts do not already limit; LinkedIn is still unreadable without Exa). One provenance
  failure caught by the scorer: the model recorded a department that the archived page never states.
  Admission now rejects a value that says more than its quoted line (same rule in the scorer). 1.62
  dollars. Rung 6 ran out of order (before 5) because the Exa key is still empty.

- Rungs 5 and 7 (2026-09-04) ran but every run ended with stop_reason=error: the OpenRouter key hit its
  100 dollar limit mid-run (limit_remaining 0.93). The partial rows are kept and marked error; they must
  be rerun once credits exist. Requests now send max_tokens=6000 so a low balance cannot reject calls
  on affordability alone.

## In progress
- Waiting on EXA_API_KEY and FIRECRAWL_API_KEY for rungs 5 to 9 and the collision targets.

## Next
- Stages 2 to 10 per the plan file.

## Blocked on Rayyan
- EXA_API_KEY (dashboard.exa.ai) and FIRECRAWL_API_KEY into .env. Exa blocks the collision-pair
  script in Stage 1.
- Confirm one same-name same-school pair from evals/find_collisions.py output (targets 4 and 5 are
  skipped by the ladder until then).
- Confirm the Ariglad CTO from the public source I will show.
