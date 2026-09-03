# Progress

## Done
- Stage 0 (2026-09-03): folder, uv project on Python 3.12, salvage of resolution.py, trace.py,
  workspace.py, graph.py, schema.py and their tests from v1; evals/score.py with the full formula
  (identity branches, recall, contradiction / decoy / provenance penalties); evals/v1_adapter.py;
  evals/results.py (ladder.jsonl, ladder.md, spend.json). Calibration row rung=v1-calib recorded:
  the new scorer reproduces v1's number on v1's saved report, net 0.534, core 78 / deep 38 /
  surprise 0, identity PASS, provenance not checked (v1 findings carry no excerpt).

## In progress
- Stage 1: ladder.py, evidence.py, record_claim, record_candidate, budget.py, llm.py, minimal
  report.py and agent.py for TOOLS=none, the 9 golden entries, rung 1.

## Next
- Stages 2 to 10 per the plan file.

## Blocked on Rayyan
- EXA_API_KEY (dashboard.exa.ai) and FIRECRAWL_API_KEY into .env. Exa blocks the collision-pair
  script in Stage 1.
- Confirm one same-name same-school pair from evals/find_collisions.py output.
- Confirm the Ariglad CTO from the public source I will show.
