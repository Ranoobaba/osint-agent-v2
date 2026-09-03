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

## In progress
- Stage 3: input-shape hardening (bare token = handle, hard-key targets resolve on their key,
  NUDGE_INPUT_SHAPE first moves), rung 3.

## Next
- Stages 2 to 10 per the plan file.

## Blocked on Rayyan
- EXA_API_KEY (dashboard.exa.ai) and FIRECRAWL_API_KEY into .env. Exa blocks the collision-pair
  script in Stage 1.
- Confirm one same-name same-school pair from evals/find_collisions.py output (targets 4 and 5 are
  skipped by the ladder until then).
- Confirm the Ariglad CTO from the public source I will show.
