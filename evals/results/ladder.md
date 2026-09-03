# Ladder results

Generated 2026-09-03T23:08:41+00:00. Noise band 0.030 (largest within-rung spread of baseline repeats, floor 0.03). Ladder spend $0.38, dev spend $0.08.

| rung | score | min | vs | delta | moved | targets | runs | identity pass | prov fail | decoy leak | cost | time |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v1-calib | 0.534 | 0.534 |  |  |  | 1 | 1 | 1/1 | 0 | 0 | $3.02 | 728s |
| dev-1 | 0.000 | 0.000 |  |  |  | 1 | 1 | 0/1 | 0 | 0 | $0.08 | 40s |
| 1 | 0.286 | 0.000 |  |  |  | 7 | 9 | 2/9 | 0 | 0 | $0.38 | 261s |

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
