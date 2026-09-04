# Ladder results

Generated 2026-09-04T00:51:57+00:00. Noise band 0.030 (largest within-rung spread of baseline repeats, floor 0.03). Ladder spend $11.89, dev spend $2.25.

| rung | score | min | vs | delta | moved | targets | runs | identity pass | prov fail | decoy leak | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1-calib | 0.534 | 0.534 |  |  |  | 1 | 1 | 1/1 | 0 | 0 | $3.02 | 728s |
| dev-1 | 0.000 | 0.000 |  |  |  | 1 | 1 | 0/1 | 0 | 0 | $0.08 | 40s |
| 1 | 0.286 | 0.000 |  |  |  | 7 | 9 | 2/9 | 0 | 0 | $0.38 | 261s |
| dev-2 | 0.129 | 0.129 | 1 | +0.129 on 1 | yes | 1 | 3 | 0/3 | 0 | 0 | $2.17 | 748s |
| 2 | 0.541 | 0.129 | 1 | +0.256 on 7 | yes | 7 | 9 | 5/9 | 0 | 0 | $4.31 | 2726s |
| 3 | 0.555 | 0.129 | 2 | +0.014 on 7 | no | 7 | 7 | 6/7 | 0 | 0 | $3.45 | 2193s |
| 4 | 0.788 | 0.483 | 3 | +0.294 on 3 | yes | 3 | 3 | 3/3 | 0 | 0 | $2.12 | 737s |
| 6 | 0.382 | 0.000 | 3 | -0.112 on 3 | no | 3 | 3 | 2/3 | 2 | 0 | $1.62 | 896s |

## Per run

| rung | target | run | net | identity | recall | wrong | prov fail | decoy | admitted | rejected | calls | cost | time | stop | sha | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1-calib | baseline | 1 | 0.534 | resolved ok | 0.534 | 0.0 | 0 | 0 | 27 | 0 | 50 | $3.02 | 727s | budget | v1:1c3d | v1 report scored by the v2 scorer; provenance not checked (no excerpts in v1) |
| dev-1 | baseline | 1 | 0.000 | ambiguous | 0.000 | 0.0 | 0 | 0 | 0 | 5 | 7 | $0.08 | 39s | finish | 4b13de7 | smoke |
| 1 | baseline | 1 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 6 | 0 | $0.07 | 27s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | baseline | 3 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 1 | 0 | $0.04 | 31s | saturation | 6263deb | stage 1: raw Opus, no tools |
| 1 | baseline | 2 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 4 | 0 | $0.05 | 34s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | email_only | 1 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 1 | 0 | $0.03 | 23s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | sarah_chen | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 0 | 0 | 0 | $0.02 | 16s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | handle_only | 1 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 1 | 0 | $0.04 | 31s | saturation | 6263deb | stage 1: raw Opus, no tools |
| 1 | ariglad_cto | 1 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 2 | 0 | $0.04 | 30s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | invented | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 0 | 4 | 0 | $0.04 | 25s | finish | 6263deb | stage 1: raw Opus, no tools |
| 1 | michael_jordan | 1 | 0.000 | unresolved | 0.000 | 0.0 | 0 | 0 | 0 | 3 | 0 | $0.06 | 39s | finish | 6263deb | stage 1: raw Opus, no tools |
| dev-2 | baseline | 1 | 0.000 | ambiguous | 0.000 | 0.0 | 0 | 0 | 0 | 4 | 8 | $0.22 | 135s | saturation | e04cd42 | stage 2 smoke |
| dev-2 | baseline | 1 | 0.129 | ambiguous | 0.259 | 0.0 | 0 | 0 | 32 | 1 | 18 | $1.38 | 309s | budget:usd | 14e4043 | stage 2 smoke 2 |
| dev-2 | baseline | 1 | 0.129 | ambiguous | 0.259 | 0.0 | 0 | 0 | 23 | 1 | 17 | $0.56 | 303s | finish | 12fb566 | smoke 3, no pruning |
| 2 | baseline | 3 | 0.129 | ambiguous | 0.259 | 0.0 | 0 | 0 | 20 | 0 | 16 | $0.51 | 256s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | baseline | 2 | 0.129 | ambiguous | 0.259 | 0.0 | 0 | 0 | 24 | 0 | 19 | $0.58 | 297s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | baseline | 1 | 0.147 | ambiguous | 0.293 | 0.0 | 0 | 0 | 23 | 1 | 19 | $0.52 | 342s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | handle_only | 1 | 0.147 | unresolved | 0.293 | 0.0 | 0 | 0 | 28 | 0 | 17 | $0.50 | 300s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | email_only | 1 | 0.328 | resolved ok | 0.328 | 0.0 | 0 | 0 | 28 | 1 | 16 | $0.49 | 355s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | sarah_chen | 1 | 1.000 | ambiguous ok | 0.000 | 0.0 | 0 | 0 | 10 | 0 | 20 | $0.39 | 319s | budget:calls | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | invented | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 6 | 0 | 16 | $0.19 | 187s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | michael_jordan | 1 | 0.471 | resolved ok | 0.471 | 0.0 | 0 | 0 | 50 | 0 | 18 | $0.69 | 324s | finish | 8c1857c | stage 2: free OSINT tools, no pruning |
| 2 | ariglad_cto | 1 | 0.714 | resolved ok | 0.714 | 0.0 | 0 | 0 | 22 | 0 | 20 | $0.43 | 343s | budget:calls | 8c1857c | stage 2: free OSINT tools, no pruning |
| 3 | baseline | 1 | 0.129 | ambiguous | 0.259 | 0.0 | 0 | 0 | 23 | 0 | 16 | $0.51 | 263s | finish | 6726021 | stage 3: input-shape hardening |
| 3 | email_only | 1 | 0.328 | resolved ok | 0.328 | 0.0 | 0 | 0 | 32 | 0 | 17 | $0.59 | 291s | finish | 6726021 | stage 3: input-shape hardening |
| 3 | handle_only | 1 | 0.362 | resolved ok | 0.362 | 0.0 | 0 | 0 | 33 | 0 | 17 | $0.55 | 354s | finish | 6726021 | stage 3: input-shape hardening |
| 4 | invented | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 6 | 1 | 15 | $0.33 | 160s | finish | 865682f | stage 4: plus Perplexity |
| 3 | invented | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 5 | 0 | 15 | $0.21 | 214s | finish | 865682f | stage 3: input-shape hardening |
| 4 | michael_jordan | 1 | 0.882 | resolved ok | 0.882 | 0.0 | 0 | 0 | 53 | 2 | 16 | $0.91 | 282s | finish | 865682f | stage 4: plus Perplexity |
| 3 | sarah_chen | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 13 | 0 | 19 | $0.45 | 295s | finish | 865682f | stage 3: input-shape hardening |
| 4 | baseline | 1 | 0.483 | resolved ok | 0.483 | 0.0 | 0 | 0 | 51 | 1 | 17 | $0.88 | 294s | finish | 865682f | stage 4: plus Perplexity |
| 3 | michael_jordan | 1 | 0.353 | resolved ok | 0.353 | 0.0 | 0 | 0 | 42 | 0 | 16 | $0.68 | 419s | finish | 865682f | stage 3: input-shape hardening |
| 3 | ariglad_cto | 1 | 0.714 | resolved ok | 0.714 | 0.0 | 0 | 0 | 24 | 1 | 20 | $0.46 | 353s | budget:calls | 865682f | stage 3: input-shape hardening |
| 6 | invented | 1 | 1.000 | unresolved ok | 0.000 | 0.0 | 0 | 0 | 5 | 0 | 17 | $0.23 | 254s | finish | 9929933 | stage 6: plus Firecrawl |
| 6 | baseline | 1 | 0.147 | ambiguous | 0.293 | 0.0 | 0 | 0 | 21 | 1 | 19 | $0.56 | 280s | finish | 9929933 | stage 6: plus Firecrawl |
| 6 | michael_jordan | 1 | 0.000 | resolved ok | 0.353 | 4.0 | 2 | 0 | 47 | 1 | 17 | $0.83 | 361s | finish | 9929933 | stage 6: plus Firecrawl |
