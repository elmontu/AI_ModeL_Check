# Detailed local framework verification — 10 September 2026

The supported local educational workflow completed end to end in a freshly
installed console environment. The final option matrix is PASS. This verifies
workflow behavior and retained evidence; it does not certify model safety,
independent agency review or release authorization.

[Every option and adversary result](../reproduction/local-framework-validation/validation-report.md)
and [complete machine-readable metrics](../reproduction/local-framework-validation/validation-report.json)
are retained with source hashes and runtime versions. All 22 trained candidates
and their reassessments remained **inconclusive**, because a membership floor or
screen does not provide a complete-interface privacy ceiling.

## Gaps repaired

| Finding | Implemented behavior | Verification |
| --- | --- | --- |
| Raw membership scores and training inputs were not fully bound into local reassessment | Hash-bound supporting manifest; split, chronology, threshold and count replay; frozen source/runtime/configuration snapshots | Changed scores, data, configuration and source are rejected; independently rehashed false counts also fail |
| Export checks reused in-memory preprocessing | Reload and verify the complete model/scaler bundle on raw inputs; each retained parent contains its scaler | Predictions and preprocessing match; base and component exports work independently |
| Fine-tuning preprocessing observed the derivative population too early | Fit the base scaler on its base-training subset | Frozen subset and parent artifacts verified |
| Nonzero class labels could index the wrong probability column | Explicit label-to-column mapping and strict array/prediction validation | Nonzero labels, invalid probabilities and mismatched shapes covered |
| Poisoning was unnecessarily restricted to binary labels | Cyclic multiclass label poisoning and fixed-target backdoors for bounded supported estimators | Matched clean retraining, declared recipes, repeat seeds and original-candidate immutability |
| Regression lacked adaptive attacks and durable tool failures | Scalar-output adversarial search, matched random baselines, controls and per-tool error results | Leaking regressor, malformed predictions, nonfinite data and deterministic budgets covered |
| Language failures could lose the report or obscure partial leakage | Retain controls and provider responses; record truncation/timeouts/model changes as incomplete; retain detected partial leaks | Deliberately leaking model, failed controls, swaps, truncation and inert tool requests covered |
| Successful training could obscure poor predictive quality | Non-XGBoost public presets compare with training-only majority/mean baselines and emit utility warnings | Baselines recomputed from frozen train/test arrays; weak MLP/wine result visible in browser |
| Evidence could only be located by filesystem path | Artifact browser, individual downloads and manifest-backed ZIPs | Every generated training and reassessment download checked against hashes and ZIP contents |
| Review cases could not bind documents directly | Bind files in both modes; show paths, hashes and replay support | Missing review documents rejected, then synthetic documents bound and reassessment repeated |
| Retry/cancellation and failure diagnostics were incomplete | Queued cancellation, explicit retry as a new attempt, preserved options/history and failed-run artifacts | Atomic claims, active-case guards, null-heartbeat recovery and retained diagnostics covered |

## Executed coverage

| Check | Result |
| --- | --- |
| Fresh console installation | Passed; no existing environment overwritten; dependency check clean |
| Every model/dataset selection | 40 PASS: 22 actual training combinations, 18 expected invalid-pair rejections |
| Case kind × release route × mode | 36 PASS: intake, required slots and missing-evidence refusal |
| Every trained case | Required bindings, education assessment, review-mode refusal/completion, reassessment, tamper refusal and restoration passed |
| Artifact export | Every training and assessment file SHA-256 checked; ZIP manifest and contents verified |
| Reference lifecycle scenarios | All 8 executed |
| Related experiments | 13 retained derivative, joint-component and image-translation reports |
| Local language options | Both installed Qwen models: 9 attacks and 2 controls each; all executions and controls complete |
| Main suite in fresh console environment | 745 tests, zero failures; 18 skips (17 optional runtime, 1 Windows symlink capability) |
| Additional CPU optional runtime | 66 tests, zero failures or skips; executes all 17 dependency-skipped tests above |
| Academic consistency suite | 43 tests passed |
| Schema replay | All 37 current schemas and manifest verified |
| Python compilation / JavaScript syntax | Passed |
| Docker execution | Not run: local Docker daemon unavailable |
| Lean proof rebuild | Not run: pinned Lake/Lean toolchain unavailable |

The optional suites used CPU torch 2.13.0+cpu and torchvision 0.28.0+cpu.
They test bounded hook/worker contracts; they do not constitute large-model
training or a real agency field trial. The single platform-specific symlink
check remains skipped on this Windows host.

## Adversary execution matrix

The 226 tabular/regression tool invocations comprise **193 completed, 33
unsupported, zero failed**. Completion means an experiment ran; it is not a
universal pass/fail risk threshold. Unsupported results remain visible.

| Adversary/tool group | Completed | Unsupported | Failed |
| --- | ---: | ---: | ---: |
| structural disclosure | 17 | 3 | 0 |
| worst case membership | 20 | 0 | 0 |
| membership score attacks | 20 | 0 | 0 |
| model extraction | 20 | 0 | 0 |
| attribute inference | 20 | 0 | 0 |
| numeric robustness | 20 | 0 | 0 |
| label only membership | 20 | 0 | 0 |
| adaptive adversarial search | 20 | 0 | 0 |
| tree leaf exposure | 4 | 16 | 0 |
| label poisoning | 13 | 7 | 0 |
| trigger backdoor | 13 | 7 | 0 |
| regression loss membership | 2 | 0 | 0 |
| regression extraction | 2 | 0 | 0 |
| regression perturbation | 2 | 0 | 0 |

Unsupported cases are leaf exposure on non-tree estimators, controlled retraining
for the SVM/CNN/ensemble adapters, and composite structural parameter accounting.
They are not converted into successful coverage. The JSON report preserves each
attack's configuration, budgets, baseline, measurements and assumptions for
every model/dataset pair, plus related derivative/component/image measurements.

Each installed language model recorded two violations: retrieved-answer
contamination and an unauthorized inert tool request. Both controls
passed. No tool was executed and no agency data were used. Fixed synthetic
contexts test instruction handling, not actual training-record memorization.

One utility finding is intentionally retained: MLP on wine achieved **38.10%**
held-out accuracy against a **39.68%** training-majority baseline. Its baseline
flag and warning are shown in the console. The model and split were not retuned
after inspecting this held-out result.

## Reproduce the workflow

```console
python scripts/setup_pipeline.py --profile console --venv .local/my-test-runtime
```

Use that environment's Python from the source checkout:

```console
python scripts/validate_framework_e2e.py --output output/new-validation
python scripts/validate_framework_e2e.py --output output/new-language-validation --language-model YOUR_INSTALLED_MODEL
python -m unittest discover -s tests -v
python -m unittest discover -s academic/tests -v
```

The runner creates an isolated persistent store. It never mutates existing
console cases, and refuses an existing output directory. Each candidate tamper
test restores the original bytes in a finally block. All matrix runs record
source hashes before/after execution and fail if sources change during the run.
CI now runs the offline matrix on Linux and uploads its evidence, including on
failure. This local report does not claim that the new CI run has executed.

## Retained evidence and practical boundaries

The [retained evidence index](../reproduction/local-framework-validation/README.md)
links exact logs, runtime inventory and hashes. Raw job trees remain locally at
`output/framework-e2e-final-20260910/workspace/`. They include models, frozen data,
attack scores, responses, preflight attempts and assessment audit records.

Browser verification used the fresh runtime at port 8765. It trained a fine-tuned
wine model, browsed its 32 evidence files, trained the weak MLP example, displayed
the utility warning and supporting replay binding, switched review modes, and
submitted reassessment. Existing console cases and run history were preserved.

Local replay verifies bookkeeping and hash consistency; it cannot independently
prove model execution or agency custody. Legacy v1.0.0 runs remain readable but
do not gain the new v1.1.0 replay checks retrospectively. Review documents in the
matrix are marked synthetic and are never treated as agency approvals.

Remaining work includes live retrieval/agent execution, large-model fine-tuning
in the console, audio/diffusion workers, broader adaptive language corpora,
registered evidence for the exploratory tools, complete-interface privacy
ceilings and production operations. ZIPs are limited to 64 MiB, running jobs
cannot be cancelled, and external bound case inputs are not copied into ZIPs.
