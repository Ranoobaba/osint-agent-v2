# Autoresearch program for osint-agent-v2

One experiment per invocation. The agent forgets; the repo remembers. Read this file, results.tsv,
LEARNINGS.md and `git log --oneline -15` before doing anything.

## Objective

Raise `net` on the mini-eval without touching the ruler. `net` is the mean over three public golden
targets (michael_jordan, ariglad_cto, invented) of the ladder scorer's per-target score, at the shipped
configuration (autoresearch/eval.py runs it). Secondary metrics are logged, not optimized:
rejection rate (rejected / proposed claims), admitted findings per data call, dollars per admitted
finding, mean cost, mean duration.

## Hard rules

- A change is KEPT only if: net rises by more than the noise band (0.03), provenance failures are 0,
  decoy leaks are 0, and mean cost per run stays under the cap in config (MAX_USD). Otherwise REVERT.
- Never edit: evals/score.py, evals/golden.local.jsonl, src/osint2/evidence.py (admission), src/osint2/
  resolution.py, src/osint2/budget.py, the caps in .env. Editing those changes the ruler, not the agent.
- May edit: src/osint2/agent.py (SYSTEM_PROMPT, recitation), src/osint2/deepdive.py (lead selection,
  SUB_PROMPT, shares), src/osint2/entities.py (frontier ordering only), tool descriptions in src/osint2/
  tools/*.py, and NUDGE_* flags in .env.
- One change per experiment. Small and reversible. Describe it in one line.
- Spend guard: eval.py refuses to run when autoresearch spend (autoresearch/spend.json) would pass
  AUTORESEARCH_CAP_USD (default 6). If it refuses, write the idea to LEARNINGS.md under "Untested ideas"
  and stop.
- If a STOP file exists in autoresearch/, do not start an experiment.

## Procedure

1. Read state (this file, results.tsv, LEARNINGS.md, git log). Pick ONE idea, preferring ideas the
   ledger has not tried and that the last loss suggests.
2. Make the change. Run `uv run pytest -q`; if red, fix or revert before spending money.
3. Run `uv run python autoresearch/eval.py --note "<one line>"`. It prints the row it appended.
4. Decide with the hard rules. If kept: `git commit -am "ar: <one line> (net a -> b)"`. If reverted:
   `git checkout -- .` and record the loss in results.tsv (eval.py already wrote the row; set status).
5. Append one line to LEARNINGS.md: what was tried, what happened, why (mechanism, not vibes).
6. Exit. Do not start a second experiment in the same invocation.

## Ideas queue (strike through when tried)

- Recitation: list the top 3 frontier leads with a suggested tool call each, instead of a prose line.
- Prompt: ask for record_claim after EVERY data tool result (recorded facts are the score; delayed
  recording gets cut by the budget).
- Deep dive: give the connection lead the share of two leads when the frontier has a person with a
  handle (identified connections scored highest per dollar in the Kunal runs).
- Prompt: one value per claim, quoted line must contain it (rejection rate is wasted budget).
- Frontier: put unread accounts on hosts Exa can serve ahead of bare-name people.
- Tool descriptions: web_search should say when to use category='linkedin profile' vs plain search.
- Recitation: show which golden-like categories are still empty (professional, education, contact,
  online presence, personal, connections) so the model spends calls on empty ones.
