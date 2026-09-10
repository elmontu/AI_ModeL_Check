# Framework execution coverage

Current detailed validation: [745-test suite, complete option matrix and adversary results](framework-e2e-validation-2026-09-10.md). The matrix exercised 22 supported training combinations, 18 invalid pairings and both installed language-model options; all behaved as expected.

This inventory describes the local educational pre-POC. Model catalog entries
are broader than implemented trainers. Completing attacks does not approve release.

| Family | Console execution | Sample | Evidence |
| --- | --- | --- | --- |
| XGBoost | Train and test | Breast cancer | Registered membership; 11 exploratory tool groups |
| Logistic, random forest, MLP, SVM | Train and test | Breast cancer, wine, digits | Registered membership; explicit unsupported attack adapters |
| Fine-tuned MLP | Train base and warm-start derivative | Classification datasets | Registered derivative assessment, base lineage, privacy comparison |
| Voting ensemble | Train and combine components | Classification datasets | Registered assessment, component and joint-access probes |
| Small CNN | Train convolution kernels on CPU | Digits | Registered membership, generic attacks, image translations |
| Ridge and forest regression | Train and test | Diabetes | Registered membership, extraction, robustness |
| Local Ollama language model | Test an installed model | Synthetic prompts | Nine attacks, two controls, response artifacts |
| RAG context and agent interfaces | Synthetic passages and inert tool schemas | Synthetic fixtures | Injection, contamination, tool requests and multi-turn pressure |
| Larger vision/LLM training | Separate experiment scripts | Profile-dependent | Not integrated into the wizard |
| Audio and diffusion | No console adapter | None bundled | Not implemented |

## Training workflow

Ten presets and four bundled datasets are available. Supported pairs are validated.
The split and membership plan are frozen before training. Scaling uses training
records only. Exports are reloaded and checked for prediction equivalence. Each
run saves utility, attack, lineage and assessment artifacts and an Education case
with the required bindings. Convergence warnings are retained.

The registered assessment covers one loss-based membership attack, with separate
nonmember calibration and audit partitions. Broader attacks remain exploratory;
they are not silently admitted as registered attack-battery evidence. No preset
provides a complete-interface privacy ceiling or authorizes release.

Fine-tuning retains the base model before warm-start training. Comparisons use
the derivative's membership population; because the base trained on a subset,
its result is a transfer baseline, not base membership accuracy. Ensemble reports
bind both component hashes and compare a predefined maximum true-class-confidence
attack under joint component access. Neither comparison exhausts possible attacks.

## Language tests

The native console discovers models installed at http://127.0.0.1:11434; it does
not download models. The runner binds model digests before and after execution
and retains synthetic responses. Benign-following and unprotected-canary controls
must succeed for coverage to be complete. Detection includes literal, whitespace,
base64 and ROT13 variants; human review remains necessary.

The nine cases cover direct disclosure, instruction override, role spoofing,
encoded/fragmented extraction, retrieved-context injection, answer contamination,
inert agent-action requests and multi-turn pressure. These do not measure actual
training-record extraction or run real tools. Host Ollama is supported by the
native launcher; container loopback does not reach the host's Ollama service.

## Remaining research and deployment work

- Live retrieval-index and real agent adapters, adaptive language attacks,
  training-data memorization probes and independent human scoring.
- Large language/vision fine-tuning in the wizard, audio and diffusion adapters.
- Complete-interface privacy ceilings and calibrated registered evidence for
  exploratory tools; exhaustive derivative and composition analysis.
- Agency-specific data, threats and release criteria, independent review and
  production identity, isolation and operations.

These are explicit scope limits. The local teaching workflow does not implement
every family in the protocol catalog. Use **View support and gaps** or
`GET /api/capabilities` for the runtime inventory.

## Earlier validation on 10 September 2026 (superseded by the detailed report)

The full suite ran **714 tests in 154.900 seconds: OK, 18 skipped**. Previous
finite-channel failures were fixed by retaining the prior-only guessing floor
in the reference experiment; production gates were not weakened. Full output:
`output/framework-completion-20260910/unittest.log`.

Integration tests trained all nine non-XGBoost presets and validated their exports
and registered requests. Existing XGBoost tests also passed. An actual small CNN
obtained 0.9698 digits held-out accuracy. Actual local `qwen2.5-coder:14b-64k`
testing completed nine cases and both controls and recorded two violations;
this is evidence for review, not a safety pass.

The final API payload regression test also passed with all 17 console tests.
Browser verification submitted a language job (two observed violations, controls
passed), trained ridge regression on diabetes, confirmed all required case
bindings, and submitted a separate reassessment. Markdown checks found no missing
local targets across 37 documentation files. Docker image execution and optional
large-model training were not validated in this runtime.
