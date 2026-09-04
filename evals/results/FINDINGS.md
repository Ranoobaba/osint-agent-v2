# What the ladder showed, and what it did not

Written 2026-09-04 after the OpenRouter key hit its limit. Rungs 1 to 7 ran; rungs 8, 9 and the
budget sweep did not. The table (ladder.md) is the evidence; this page is the reading of it, with every
inference labeled as one.

## Measured

| rung | configuration | targets | score | vs | delta on the same targets | moved | identity pass | provenance failures | decoy leaks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | raw Opus, no tools | 9 | 0.222 | | | | 2/11 | 0 | 0 |
| 2 | plus GitHub, Gravatar, Wayback, whatsmyname | 9 | 0.495 | 1 | +0.273 | yes | 6/11 | 0 | 0 |
| 3 | plus input-shape hardening | 9 | 0.506 | 2 | +0.011 | no | 7/9 | 0 | 0 |
| 4 | plus Perplexity | 4 | 0.841 | 3 | +0.429 | yes | 4/4 | 0 | 0 |
| 5 | plus Exa (runs cut short by the key) | 4 | 0.816 | 3 | +0.404 | yes | 4/4 | 0 | 0 |
| 6 | plus Firecrawl | 4 | 0.416 | 3 | +0.004 on 4 | no | 3/4 | 0 | 0 |
| 7 | Perplexity plus Exa (runs cut short by the key) | 4 | 0.847 | best of 4, 5 | +0.006 | no | 4/4 | 0 | 0 |

Noise band: 0.030 (the three baseline repeats at rung 2 spread 0.018, so the floor applies).
Spend: ladder $19.24, development $2.25, total OpenRouter usage on the key $99.07 of $100 (v1 used
the rest before this rebuild).

1. **Tools beat memory by a wide margin.** With no tools, every claim Opus proposed was rejected for
   lack of a source and every resolvable target scored 0. Rung 1's 0.222 is entirely the two abstain
   targets rewarding an empty report.
2. **The free OSINT chain is the largest single gain (+0.273).** GitHub commit metadata recovered the
   author's real email on the email-only target and resolved it; the Ariglad CTO resolved at recall
   0.71 with no web search at all. This is the tactic a general LLM cannot perform.
3. **Web search is the second gain (+0.43 on the subset).** Perplexity resolves the author's own
   baseline (it corroborates employer and location across two domains) and takes Michael Jordan from
   0.35 to 0.88 and the with-key collision target to 1.0 with zero decoy leaks.
4. **Rung 6 did not measure Firecrawl.** Every fetch_page call in every rung 6 run returned an HTTP
   error: the Firecrawl key in .env is rejected by Firecrawl's API (401, verified directly on
   2026-09-04). The rung therefore measured rung 3's tool set plus a tool that always failed, and its
   score is inside the band of rung 3 as expected. "Firecrawl adds nothing" is NOT a finding of this
   ladder; it is untested. Two earlier corrections stand: the run's two provenance failures were a
   report-layer dedupe bug, since fixed, and the admission rule that a value may not say more than
   its quoted line stays because it blocks real embellishment. Tools that fail with an auth error are
   now removed from the model's tool list for the rest of the run, so a dead key can no longer burn a
   fifth of the call budget the way it did here.
5. **Input-shape hardening did not move the group score (+0.011)**, though its resolver rule fixed the
   handle-only target (0.147 to 0.362). The rule is kept as a correctness fix; the recitation nudge is
   unproven.
6. **Identity never went wrong.** Across 51 scored runs, no run resolved to the wrong person and no
   finding about a same-name decoy was attributed to the target. Ambiguity was reported honestly on
   every collision-without-key run.
7. **Provenance held.** Zero provenance failures in 51 runs after the dedupe fix; the two once recorded
   were a report-layer merge bug, caught by the scorer and corrected.

## Inferred (not measured)

- **Shipped configuration (updated 2026-09-04): all free tools (GitHub, Gravatar, Wayback, whatsmyname,
  OpenAlex, Roblox, Tinder web profiles, holehe, people-search snippets) plus Perplexity, Exa and
  Firecrawl, deep dive ON, 40 calls, $2.50, 25 minutes.** This is NOT a ladder result. It was chosen after
  the depth pass on a second key: single runs on one target (Kunal Baldava) went 35 findings at the old
  configuration, 50 with the entity-graph frontier, 65 with the deep dive at 40 calls, with 0 provenance
  failures and 0 leaks each time, and a fully identified collaborator only the deep dive produced. The
  autoresearch baseline on three golden targets at this configuration scored 0.902 (mean of 0.706, 1.0,
  1.0) at $1.68 per run. Per-target noise is about 0.12 on a single run; none of these are repeats.
- **Rung 8 (all three) would not beat rung 7.** Firecrawl was neutral to negative on its own and covers
  no page the other two cannot. This is an inference from rung 6, not a measurement of rung 8.
- **Rung 9 (deep-dive subagents) is unmeasured on the ladder.** The single-run evidence above is why it
  ships on; a 9-target rung with repeats would cost about $17 and has not been run.
- **The budget sweep did not run.** 40 calls ships because the one 40-call run found 15 more admitted
  findings than the one 24-call run on the same target, not because a knee was measured.

## What would settle the inferences

About $33 on the OpenRouter key: rerun rungs 5 and 7 cleanly ($5), rung 8 on all nine targets ($12),
rung 9 ($12 with the extra repeats cut), the 40-call sweep point ($2.50), and one deployed-parity run
($1). The ladder runner enforces the cap and the cut order; the commands are in the README.
