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

- Closed out 2026-09-04 with no money left: Ariglad CTO confirmed by Rayyan (Ali Avci). Shipped
  configuration set from the measured rungs (free tools + Perplexity + Exa, no Firecrawl, DEEP_DIVE=0)
  and deployed. Five examples packaged from clean runs with private emails hashed; offline replay check
  passes 49/49 on michael_jordan. evals/results/FINDINGS.md separates what was measured from what is
  inferred; rungs 8, 9 and the sweep are unmeasured.

- Deployed parity (2026-09-04, second key): invented person unresolved with 0 findings and 9 not_found;
  Michael Jordan resolved, 54 findings, net 0.824 with provenance verified on the served sources, 0.89
  dollars. Rung D recorded.

- Depth pass (2026-09-04, on Rayyan's own key, about 9 dollars of tests): entity graph with an unexplored
  frontier (entities.py), frontier nudge in the lead loop, connection and account leads in the deep dive
  with per-subagent call shares, OpenAlex, Roblox, Tinder web-profile, holehe email-registration and
  people_search (aggregator snippets, sensitive) tools. Measured on Kunal Baldava: 35 findings at 20 calls
  and no deep dive; 50 with the frontier nudge; 65 at 40 calls with the deep dive (1.71 dollars), where the
  subagents admitted 60 claims and took a GitHub collaborator handle to a fully identified person with
  LinkedIn, employer, location and prior roles. Shipped configuration is now 40 calls, 2.50 dollars,
  deep dive on, all free tools plus Perplexity, Exa and Firecrawl. These rungs are unmeasured on the
  ladder (no money for repeats); the numbers above are single runs. scripts/rebuild_report.py recovers a
  report from a run that died (the claims are on disk); --rederive rebuilds the entity graph.

- Autoresearch pass (2026-09-04): harness in autoresearch/ (program.md, eval.py, replay.py, loop.sh, ledger).
  Kept: dedupe keeps provenance with the richer value (found by the extractor probe; also cleared the rung 6
  provenance failures, which were this bug); per-source extractor with Haiku after resolution (offline
  recall 0.706 -> 0.824 at $0.14; live mini-eval net 0.902 -> 1.000 at lower cost per run). Shipped
  EXTRACTOR=1. Endpoint locked behind AGENT_API_KEY; the page has a key field. Architecture review
  (fresh-context subagent with Exa) in the session log; its ranked list is the ideas queue.

- Depth + cost pass (2026-09-04, three fresh-context analysts): code-driven incremental sweep after resolution
  (whatsmyname, roblox, tinder, holehe, gravatar, GitHub reverse, wayback, people_search, keyless profile
  reads for reddit/dockerhub/hackernews/keybase/chess), dead tools disabled per run, memo keys by identifier,
  frontier fixes, Exa tweet/pdf categories, extractor hygiene, notes folded into one live recitation (the
  separate note message had been breaking the prompt cache: $0.61 per run), cache breakpoint on the last tool
  result, 4k lead view, Haiku anchor, Sonnet subagents (SUB_MODEL). Kunal: 111 findings/$1.89 -> 131/$1.03,
  cache 69% -> 88%, 0 dead calls. Rung 6 corrected: Firecrawl key is invalid (401), the rung never tested it.
  Endpoint locked (AGENT_API_KEY in .env). Key balance about $6 left.

- Social/school/family sweep wave (2026-09-04, commit 6feef0b): Facebook and Instagram public profiles
  via search snippets gated on name + school/city then read through Exa; high-school and PDF searches
  read by the extractor; same-surname LinkedIn co-listings in the person's city as sensitive leads;
  US-only obituary/wedding search admitted when the snippet names the person in full. Paid sweep
  searches now charge the budget (Budget.charge_tool) but not the call cap. Live check: runs/deployed_kunal4.

- Live check runs/deployed_kunal4 (2026-09-04, $1.12, 21 steps, stop=handoff): 204 findings of which 61
  were junk from the incremental re-sweep trusting entity-graph keys (holehe label "office365" became a
  handle and whatsmyname on it admitted 57 accounts; two whatsmyname hit hosts became "domains"; a
  connection's email was swept). Fixed in f7e2463 (keys must tie to the person, registration labels are
  never handles, account_ URLs never make domain nodes, tool commentary rejected as a value; 62 tests).
  Honest count 143 findings (vs 131): Saqib Mumtaz chased to Georgia Tech, Pace Junior Science College,
  Mumbai/Hyderabad origin, Sciences Po dual degree, devpost/huggingface/soundcloud accounts, hobbies.
  Social wave correctly rejected a Facebook namesake (Kunal Agarwal); no public FB/IG profile exists.
  Confirmation run runs/deployed_kunal5 on the fixed build ($1.26, 22 steps): 127 findings, 0 junk-key
  findings, family wave ran (6 Baldava LinkedIn leads, city unverified so now field same_surname_profile),
  high_school Pace Junior Science College and CNM School. OpenRouter balance after: $2.80.

- Firecrawl key replaced 2026-09-05 and validated (scrape of example.com HTTP 200); deployed app reports
  keys.firecrawl true. The old key was the one rung 6 ran with, so rung 6 is still an untested rung.

## In progress
- Nothing running. Balance $2.80: one live run of the full configuration ($1.25) or rung 6 on its
  subset (about $1.90) would fit, not both. Remaining ladder work needs about 33 dollars of OpenRouter credit.

## Was: waiting on EXA_API_KEY and FIRECRAWL_API_KEY for rungs 5 to 9 and the collision targets.

## Next
- Stages 2 to 10 per the plan file.

## Blocked on Rayyan
- EXA_API_KEY (dashboard.exa.ai) and FIRECRAWL_API_KEY into .env. Exa blocks the collision-pair
  script in Stage 1.
- Confirm one same-name same-school pair from evals/find_collisions.py output (targets 4 and 5 are
  skipped by the ladder until then).
- Confirm the Ariglad CTO from the public source I will show.
