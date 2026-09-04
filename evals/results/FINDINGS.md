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
| 6 | plus Firecrawl | 4 | 0.328 | 3 | −0.084 | no | 3/4 | 2 | 0 |
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
4. **Firecrawl alone adds nothing (−0.084).** The pages it can render, the free tools already reach;
   the pages that matter (LinkedIn) it cannot. Its one contribution was negative: the model recorded a
   department that an archived page never stated, which the scorer caught and admission now blocks.
5. **Input-shape hardening did not move the group score (+0.011)**, though its resolver rule fixed the
   handle-only target (0.147 to 0.362). The rule is kept as a correctness fix; the recitation nudge is
   unproven.
6. **Identity never went wrong.** Across 51 scored runs, no run resolved to the wrong person and no
   finding about a same-name decoy was attributed to the target. Ambiguity was reported honestly on
   every collision-without-key run.
7. **Provenance held.** Two provenance failures in 51 runs, both from one Firecrawl run, both caught
   by the scorer before the admission rule was tightened.

## Inferred (not measured)

- **Shipped configuration: free tools plus Perplexity plus Exa, no Firecrawl, no deep dive.** Rung 7
  scored highest on the subset (0.847) but its edge over rung 4 (0.006) is inside the band, and its runs
  were cut short by the key. The honest statement is that Perplexity and Exa are each large gains and
  their combination is at least as good as either. Exa is kept because it is the only route to LinkedIn
  content (verified in v1), which the subset under-represents.
- **Rung 8 (all three) would not beat rung 7.** Firecrawl was neutral to negative on its own and covers
  no page the other two cannot. This is an inference from rung 6, not a measurement of rung 8.
- **Rung 9 (deep-dive subagents) is unmeasured.** The code exists (src/osint2/deepdive.py) and is off by
  default. v1's A/B on a pre-resolution fan-out found it leaked same-name facts; the post-resolution
  version here is pinned to the resolved candidate by construction, but its effect on recall at equal
  budget is unknown. DEEP_DIVE=0 ships.
- **The 20-call budget is the measured point.** The sweep at 40 and 80 calls did not run, so the
  shipped default stays at 20 calls, $1.25, 8 minutes, which every rung above was measured at.

## What would settle the inferences

About $33 on the OpenRouter key: rerun rungs 5 and 7 cleanly ($5), rung 8 on all nine targets ($12),
rung 9 ($12 with the extra repeats cut), the 40-call sweep point ($2.50), and one deployed-parity run
($1). The ladder runner enforces the cap and the cut order; the commands are in the README.
