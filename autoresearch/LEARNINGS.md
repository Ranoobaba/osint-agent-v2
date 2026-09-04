# LEARNINGS (autoresearch)

Append one line per experiment: what, result, why.

- 1 baseline (live, $5.04 for 3 runs at 40 calls + deep dive): net 0.902 (michael_jordan 0.706, ariglad_cto 1.0,
  invented 1.0), prov 0, decoy 0, rejection 7.1%, 1.77 findings per call, $0.028 per finding. Live iterations at the
  shipped config cost $1.68 per run; the $6 cap allows one. Offline objectives (J_replay, probes) from here on.
- J_replay baseline ($0): mean net 0.471 over 48 saved runs with recorded resolutions. The deployed-parity run
  (D/michael_jordan) has no candidates.json in its fetched copy and always shows as lost; ignore that key.
- Extractor probe ($0.66, Sonnet over 30 stored sources of the baseline michael_jordan run): recall 0.706 -> 0.824,
  305 claims admitted, 23 rejected. First scoring showed 3 provenance failures and net 0; root cause was NOT the
  extractor but dedupe_findings in report.py replacing a finding's value with a richer duplicate while keeping the
  old excerpt and source. Fixed (provenance travels with the value). After the fix: net 0.824, prov 0, decoy 0.
  Cost per source ~$0.022 at 12k chars; the review's $0.10 estimate was 6x low. Verdict: the mechanism adds recall;
  shipping it needs a cheaper extractor (Haiku, or 6k chars) and a live rung, which money does not allow now.
- Dedupe fix replayed over all saved runs (J_replay 0.471 -> 0.479): the rung 6 michael_jordan run's two
  "provenance failures" were this bug, not model embellishment. FINDINGS.md corrected.

- Extractor probe with Haiku ($0.14, same 30 sources): recall 0.706 -> 0.824, 287 admitted, 25 rejected, prov 0,
  decoy 0. Same gain as Sonnet at one fifth the cost. Wired behind EXTRACTOR=1 (post-resolution only, 6k chars,
  Haiku). Live confirmation: one 3-target eval with EXTRACTOR=1 against the 0.902 baseline; cap raised 6 -> 8
  for that single run with Rayyan's approval of "offline plus one live confirmation".

## Untested ideas
