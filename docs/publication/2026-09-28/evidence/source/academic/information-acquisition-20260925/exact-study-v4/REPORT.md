# Committed information: exact task-switch and learned-export study

The old representation is randomized response of the first bit. A later task needs the independent second bit. Both training bits belong to the protected replacement vector; target labels are public/fixed in the privacy definition.

The extension preserves the old representation exactly. Its joint channel is checked with rational arithmetic; an independent unrestricted finite LP checks the optimum. Classical DP mechanism design and binary testing supply the ingredients. Novelty is not established by these checks.

At old odds 3 and total odds 9 (epsilon log 3 and log 9), old-only accuracy for the new bit is .5; independent extra RR achieves .75; the optimal correlated extension achieves .85. Rebuilding solely for the new task would achieve .9 but cannot erase the retained old transcript.

The arms are alternative histories at log(9), paired on old records/cache with independent augmentation coins. Releasing both augmented representations together instead has exact bound log(27), verified by rational likelihood-ratio enumeration. This is not a production experiment or a global privacy statement about every synthetic run.

| Target new-bit accuracy | Minimum incremental epsilon | Independent RR incremental epsilon |
|---|---:|---:|
| 0.60 | 0.236389 | 0.405465 |
| 0.75 | 0.510826 | 1.098612 |
| 0.85 | 1.098612 | 1.734601 |
| 0.90 | 1.540445 | 2.197225 |

## Actual learning from the committed representation

Each synthetic learner estimates an unknown sign from privatized labeled training rows, then exports that sign as a predictor on legitimate new raw inputs. It never receives the raw protected training bits. Exact all-learner error comes from binary hypothesis testing, not the performance of a selected architecture.

| n | Label signal | Arm | Exact classification error | Simulation |
|---:|---:|---|---:|---:|
| 8 | 0.4 | committed_cache_only | 0.500000 | 0.500360 |
| 8 | 0.7 | committed_cache_only | 0.500000 | 0.492580 |
| 8 | 1.0 | committed_cache_only | 0.500000 | 0.497800 |
| 32 | 0.4 | committed_cache_only | 0.500000 | 0.502920 |
| 32 | 0.7 | committed_cache_only | 0.500000 | 0.501960 |
| 32 | 1.0 | committed_cache_only | 0.500000 | 0.502400 |
| 128 | 0.4 | committed_cache_only | 0.500000 | 0.502400 |
| 128 | 0.7 | committed_cache_only | 0.500000 | 0.497270 |
| 128 | 1.0 | committed_cache_only | 0.500000 | 0.493000 |
| 8 | 0.4 | independent_extension | 0.415917 | 0.417200 |
| 8 | 0.7 | independent_extension | 0.262515 | 0.259340 |
| 8 | 1.0 | independent_extension | 0.070557 | 0.070300 |
| 32 | 0.4 | independent_extension | 0.351353 | 0.349080 |
| 32 | 0.7 | independent_extension | 0.164854 | 0.165050 |
| 32 | 1.0 | independent_extension | 0.001302 | 0.000600 |
| 128 | 0.4 | independent_extension | 0.304505 | 0.304440 |
| 128 | 0.7 | independent_extension | 0.150016 | 0.150000 |
| 128 | 1.0 | independent_extension | 0.000000 | 0.000000 |
| 8 | 0.4 | optimal_committed_extension | 0.386661 | 0.386080 |
| 8 | 0.7 | optimal_committed_extension | 0.202684 | 0.200190 |
| 8 | 1.0 | optimal_committed_extension | 0.012103 | 0.013200 |
| 32 | 0.4 | optimal_committed_extension | 0.321749 | 0.321680 |
| 32 | 0.7 | optimal_committed_extension | 0.151143 | 0.151400 |
| 32 | 1.0 | optimal_committed_extension | 0.000002 | 0.000000 |
| 128 | 0.4 | optimal_committed_extension | 0.300251 | 0.300200 |
| 128 | 0.7 | optimal_committed_extension | 0.150000 | 0.150000 |
| 128 | 1.0 | optimal_committed_extension | 0.000000 | 0.000000 |

Independent LP checks: 24; maximum residual 3.33e-16. Export replay exact: true. Models exported: 27 representative fits; total simulated fits 270,000; generated training rows 15,120,000.

## Public-design protocol

A frozen rational accuracy menu is searched using exact rational binomial probabilities. The planner reads only public n, the declared distribution family, the allowed failure probability and the existing/total bounds. It does not inspect protected training values. ACCEPT_FAMILY_DESIGN means the subsequently trained orientation is correct with the declared probability under this assumed family; it is not an empirical certificate for arbitrary data or an existing artifact.

Evaluated 27 public-design decisions; 19 have a feasible menu choice. No-feasible-menu is restricted to this family and menu.

## Limits

- The full representation DP guarantee can be stronger than privacy of a particular fitted model.
- Optimality is for the two-bit fixed-marginal channel class, not all private training procedures.
- Exact learning risk is optimal for each declared channel; mechanism optimality for learning is restricted to the translation-equivariant binary-output family.
- The learning experiment knows task coordinate and signal strength; it does not learn task selection privately.
- The task switch and channel are fixed independently of protected outputs; subtracting prefix bounds is not an adaptive composition rule.
- Synthetic repetitions are independent randomizations in an assumed family, not public-corpus replication.
- Fits are independent within a cell and paired across policy arms; 270,000 realizations are not 270,000 independent underlying training panels.
- The log(9) comparison is per alternative history. Joint release of both independent-noise augmentations has exact representation bound log(27), not log(9).
- The initial representation is retained; rebuilding without it is a counterfactual lower-cost benchmark.
