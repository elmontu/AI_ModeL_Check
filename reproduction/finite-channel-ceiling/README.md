# Completed preregistered finite-channel ceiling validation

This experiment tests the central MRA ceiling claim against channels whose
Bayes-optimal guessing risk is known exactly. It is the calibration tier: the
XGBoost, CNN, and LLM names are deliberately only family labels, not claims
that these synthetic channels were measured from those models.

The frozen run completed all 1,800 registered records and passed every
criterion. Across the 1,200 primary analyzer replays it observed zero
undercoverage, zero unsafe false clears, and 400/400 correct decisions for each
safe, boundary, and unsafe role. The simultaneous upper bound for each
zero-event primary endpoint was `0.01560587`, and the role-correct lower bound
was `0.98439413`. See the retained [report](results/ground-truth-report.json)
and [manifest](results/manifest.json).

## Question and registered outcomes

At a familywise error rate of `0.05`, does the production finite-channel path
emit an upper bound that covers the exact risk, becomes narrower with more
state-conditioned observations, and resolves releases on the intended side of
a tolerance of `13/20`?

The frozen design contains exact rational channels at three policy positions:

| Role | Exact risk | Intended MRA state |
|---|---:|---|
| Safe margin | `11/20 = 0.55` | `CLEAR` |
| Boundary | `13/20 = 0.65` | `HOLD` |
| Unsafe margin | `4/5 = 0.80` | `BLOCK` |

The diagnostic tier uses 100 repetitions at 100 and 500 observations per
state. The primary tier uses 400 independent repetitions at 2,000 observations
per state. Sampling uses integer weights derived from the exact rational
channel; it does not approximate probabilities with binary floating point.

For every primary repetition the same `FiniteChannelCeilingAnalyzer` used by
MRA is replayed. One primary repetition from each role additionally traverses
source generation, source verification, policy evaluation, and
`AssuranceEngine.assess`. The report must describe this as 1,200 analyzer
replays and three full-Engine integration replays, not as 1,200 full workflows.

## Acceptance rule

All registered checks must pass without changing the configuration:

- simultaneous upper confidence bounds for ceiling undercoverage and unsafe
  false-clear are at most `0.05`;
- simultaneous lower confidence bounds for safe `CLEAR`, boundary `HOLD`, and
  unsafe `BLOCK` meet the thresholds in `config.json`;
- mean interval width decreases from 100 to 500 observations per state;
- exact results are invariant to the three family labels;
- analyzer replay matches exact arithmetic, the three full workflow states are
  reached, and all tamper checks fail closed.

The Monte Carlo evaluation intervals are Bonferroni-simultaneous over 27
predeclared endpoints: undercoverage, false-clear, and role-correct decision
power for each of nine tier/scenario/sample-size groups. They measure the
simulation study; they are not substituted for the per-release MRA ceiling.

## Run after registration

Commit the config, runner, tests, and relevant MRA source before executing the
default seed. Then run:

```bash
python scripts/run_finite_channel_ceiling_experiment.py \
  --config reproduction/finite-channel-ceiling/config.json \
  --output output/finite-channel-ceiling/ground-truth-report.json
```

The command returns nonzero if a registered claim fails. The JSON retains all
state-by-observation count rows, exact rational endpoints, decisions, confidence
bounds, source/analyzer replay checks, and limitations.

The publication resource record replaces only its absolute remote
virtual-environment prefix with `[REMOTE_VENV]`. The manifest preserves both
the original raw digest and the sanitized file digest; no metric or outcome is
changed.

## Claim boundary

Success establishes calibration and usefulness for the registered complete,
one-query finite channels under fixed-horizon IID sampling. It does not show
that an ordinary model API is finite or complete, that a live service enforces
the declared interface, or that any XGBoost, CNN, or LLM deployment is safe.
Those questions are addressed only conditionally in the separate model-backed
experiment.
