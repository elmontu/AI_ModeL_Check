# Preregistered model-backed finite-channel experiment

This experiment asks whether an MRA ceiling is both sound and decision-useful
on newly trained models and real public datasets. It is intentionally scoped to
a closed hidden-record benchmark wrapper; it is not an assessment of an
ordinary prediction API or an interactive LLM.

## Fresh model/data stage

The registered collector trains three outcome-new targets with a new seed:

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

Because each state pool is finite, the aggregate population defines an exact
Bayes-risk oracle. The audit then draws with replacement and sends the counts
through simultaneous Clopper--Pearson evidence generation, portfolio
compilation, analytic solving, source verification, the production analyzer,
and the Engine.

Two interfaces are preregistered for each model:

- `raw_bins`: the categorical loss-bin symbol;
- `erasure_0p9`: the same channel followed by 90% state-independent erasure.

The erasure arm tests the protocol consequence of releasing less information.
Its exact risk must not increase. This comparison does not establish a general
causal law for arbitrary metadata or context changes.

## Soundness and usefulness criteria

The six model/interface families each have a one-shot full-Engine replay and
200 independent repeated audit samples of 5,000 observations per state. The
registered outcome is accepted only if every criterion in `config.json` passes,
including:

- all exact finite-pool oracle risks are covered;
- every repeated family has an acceptable simultaneous upper confidence bound
  on undercoverage;
- ceilings resolve the registered safe benchmark as `CLEAR` often enough to
  meet the frozen decision-power requirement;
- every source/analyzer/Engine replay and executable wrapper conformance check
  succeeds;
- four interface, count, prior, and alphabet controls fail closed;
- no raw score array is retained in the result tree.

Coverage without resolution is not sufficient: a ceiling of `1.0` cannot pass
the registered clear-rate criteria.

## Run after registration

Commit the design and source bindings before inspecting the fresh-seed outcome.
With the public datasets already cached, run:

```bash
python scripts/run_model_backed_finite_channel.py \
  --config reproduction/model-backed-finite-channel/config.json \
  --cache-dir reproduction/public-privacy/raw \
  --output-dir output/model-backed-finite-channel/fresh-run
```

The command writes the aggregate report even when acceptance fails and returns
exit status `2` for a completed but failed registered experiment.

## Claim boundary

The result is conditional on one training seed, the exact finite target pools,
the enforced categorical benchmark abstraction, and the registered sampling
model. It does not prove privacy for another artifact, arbitrary-candidate
access, text generation, a real LLM, model download, timing, side channels, or a
production population. It grants no release authorization.
