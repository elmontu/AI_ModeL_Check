# Model-backed finite-channel experiments

This experiment asks whether an MRA ceiling is both sound and decision-useful
on newly trained models and real public datasets. It is intentionally scoped to
a closed hidden-record benchmark wrapper; it is not an assessment of an
ordinary prediction API or an interactive LLM.

## Status and version boundary

`config.json` is the frozen v3 design, registered at
`2026-09-03T06:16:40Z`. Its source digests and fresh seed are fixed, and the
runner refuses changed inputs. At registration time no v3 collector output or
acceptance result had been produced.

The frozen v3 run is now complete. It passed all 10 registered criteria: six
full primary Engine replays and 1,200 repeated analyzer replays completed with
zero observed undercoverage and zero wrong-direction decisions. The
18-endpoint simultaneous upper bound for each zero-event family was
`0.02900166`; all four margin-eligible families made 200/200 correct-direction
decisions with simultaneous lower bound `0.97099834`. The canonical
[report](results/v3/model-backed-finite-channel-report.json) and
[manifest](results/v3/manifest.json) retain the result and its source hashes.

The exact v2 design is preserved as `config-v2.json` (SHA-256
`77850b333353bef86d72a1647ed0de50bf6c2d6b7ee7f6d1e26e721e653e3f8e`). Its
retained result history remains under `results/v2/`. V2 sampled through a
separate aggregate sampler and tested the wrapper surface independently; v3
therefore uses a fresh collector seed and fresh primary/repeat seed domains.
No v2 outcome is reused as a v3 outcome.

The v3 raw compact-Transformer proxy was deliberately treated as a
near-threshold case: its exact risk was `0.612857`, only `0.037143` below the
`0.65` tolerance, and it produced 31 `CLEAR` and 169 `HOLD` decisions. It was
not eligible for the preregistered `0.10`-margin resolution claim. Every v3
oracle risk was below tolerance, so v3 supplies no model-backed `BLOCK`-power
evidence; that direction is exercised only by the controlled exact-risk `0.80`
experiment.

## Fresh model/data stage

The registered collector trains three outcome-new targets with collector seed
`2026090302`:

| Family | Public dataset | Collector role |
|---|---|---|
| CNN | MNIST | Image classification |
| XGBoost | Adult Census Income | Tabular classification |
| Compact Transformer | 20 Newsgroups | Text classification; explicitly an LLM proxy only |

The collector computes member and nonmember negative log losses, hashes the
ephemeral trained artifact, and passes the raw loss arrays only through a
temporary collector directory. The experiment immediately bins the losses into
the frozen categorical alphabet. Retained experiment outputs contain aggregate
counts, dataset snapshot hashes, ephemeral artifact hashes, and model utility;
they do not contain raw losses, records, weights, prompts, or examples.

## Finite wrapper and exact oracle

The recipient supplies no candidate, prompt, model, loss, identifier, metadata,
or query path. The issuer samples one hidden record conditional on sealed `IN`
or `OUT` state and returns exactly one category. Error, timeout, non-finite, and
state-independent erasure are explicit categories, so an omitted failure path
cannot silently disappear from the transcript.

The executable conformance harness in
`src/model_release_assurance/experimental_finite_wrapper.py` checks the
zero-input, one-query surface and complete output alphabet. It is Python-level
conformance evidence, not proof of process isolation, operating-system side
channels, authentication, or a deployed endpoint.

Every primary and repeated observation is now produced by calling `query()` on
a fresh auditor-issued one-use `ClosedHiddenRecordCategoricalWrapper`
capability. A deterministic aggregate sampler is retained only as an
independent cross-replay: any exact count mismatch fails the run before a
clearance-eligible analyzer input is constructed. Each model/variant directory
contains `wrapper-execution-evidence.json`, binding the wrapper module,
interface configuration, finite population, erasure variant, seeds, aggregate
counts, conformance result, and equality checks. Both that artifact and the
mechanism evidence that names it are SHA-256 references in the portfolio
problem and are checked during Engine source replay. Individual wrapper
transcripts are not retained.

Because each state pool is finite, the aggregate population defines an exact
Bayes-risk oracle. The audit then draws with replacement and sends the counts
through simultaneous Clopper--Pearson evidence generation, portfolio
compilation, analytic solving, source verification, the production analyzer,
and the Engine.

Two interfaces are preregistered for each model:

- `raw_bins`: the categorical loss-bin symbol;
- `erasure_0p9`: the same channel followed by 90% state-independent erasure.

The erasure arm tests the protocol consequence of releasing less information.
It must satisfy the exact identity
`R(erasure_0p9) = 1/2 + (R(raw_bins) - 1/2) / 10` for every model. This
comparison does not establish a general causal law for arbitrary metadata or
context changes.

## Soundness and usefulness criteria

The six model/interface families each have a one-shot full-Engine replay and
200 independent repeated audit samples of 5,000 observations per state. The
registered outcome is accepted only if every criterion in `config.json` passes,
including:

- all exact finite-pool oracle risks are covered;
- all six simultaneous upper bounds on undercoverage and wrong-direction
  decisions are at most `0.05`;
- for every family whose exact risk is at least `0.10` from the `0.65`
  tolerance, the simultaneous lower bound on the correct-direction decision
  probability is at least `0.95`, and at least three such families resolve;
- every source/analyzer/Engine replay, wrapper conformance check, and wrapper
  versus reference-schedule equality check succeeds;
- five interface, count, prior, alphabet, and missing/tampered wrapper-evidence
  controls fail closed;
- the exact 90% erasure contraction identity holds for all three models;
- no raw score array is retained in the result tree.

Direction is role-aware: below tolerance, `CLEAR` is correct and `BLOCK` is
wrong; above tolerance, `BLOCK` is correct and `CLEAR` is wrong; `HOLD` is
neither. Near-boundary families may produce `CLEAR`, `HOLD`, or `BLOCK`, but
still must meet the wrong-direction bound. This avoids requiring all six
families to clear while retaining a quantitative usefulness test. Coverage
without resolution is not sufficient.

## Reproduction

After verifying the registration commit and strict config validation, run the
following command with the public datasets already cached:

```bash
python scripts/run_model_backed_finite_channel.py \
  --config reproduction/model-backed-finite-channel/config.json \
  --cache-dir reproduction/public-privacy/raw \
  --output-dir output/model-backed-finite-channel/fresh-run
```

The command writes the aggregate report even when acceptance fails and returns
exit status `2` for a completed but failed registered experiment.

Publication copies of the execution and resource logs replace only ephemeral
machine paths with labeled placeholders. Each manifest preserves the original
raw-log digest and the sanitized file digest; no metric or outcome is changed.

## Claim boundary

The result is conditional on one training seed, the exact finite target pools,
the enforced categorical benchmark abstraction, and the registered sampling
model. It does not prove privacy for another artifact, arbitrary-candidate
access, text generation, a real LLM, model download, timing, side channels, or a
production population. It grants no release authorization.
