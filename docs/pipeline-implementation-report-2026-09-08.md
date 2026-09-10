# Pipeline setup implementation report — 8 September 2026

The repository now has a cross-platform installer and a local case workflow
for preparing trained, fine-tuned, adapter, merged, ensemble and distilled
model releases. Start with the [quickstart](pipeline-quickstart.md).

## Gaps addressed

| Previous gap | Implemented behavior | Remaining boundary |
|---|---|---|
| Scattered setup commands and broken local environment | Standard-library bootstrap creates a new environment, installs core/training tiers and reports versions; local wheelhouse and dry-run options | Package acquisition and approved runtime selection remain operator responsibilities; existing environments are never overwritten |
| No single case entry point | Packaged `mra-workflow` supports init, bind, fingerprint, lineage, check, assess, doctor and offline demo | Local preparation and execution only; no production case-management service |
| Derivative/component identity not collected in a convenient workflow | Bound immediate parents, training/merge/router recipe, protected data manifest, overlap review, prior releases and exact candidate | No automatic inference of complete ancestry, population overlap or transferable privacy guarantees |
| Missing files or changed model inputs easy to overlook | Required-input inventory, SHA-256 replay, lineage consistency and candidate/request/access checks; input recheck after Engine execution | Hashes do not establish source truth, document adequacy or malicious-filesystem isolation |
| Output ambiguity and overwritten attempts | Unique run directories, retained preflight failures, local audit events, completion published last and explicit non-authorizing results | Source evidence is referenced rather than archived; custody, authentication and anti-rollback protection remain external |
| Setup path not exercised across platforms | Windows/Linux bootstrap and offline-demo CI job added | Remote CI was configured, not executed during this local review |

## Executed validation

A new environment was successfully installed at `.local/pipeline-runtime` on
Windows 11 with Python 3.12.14. The first sandboxed install could not reach the
package index; its partial `.venv-pipeline` directory was retained. Installation
in the separate environment then completed with the required network access.
No existing virtual environment was replaced.

- Full Python discovery: **673 tests, OK, 18 skipped**, 140.342 seconds. Skips
  concern unavailable optional PyTorch/vision/privacy experiment dependencies
  and Windows symlink capability; this is not full optional-model coverage.
- After the final completion-publication and API-parameter checks were added,
  the affected workflow suite was rerun: **16 tests, all passed**. The preceding
  full run included 13 workflow tests; it is not claimed to cover the final
  three added cases.
- Installed CLI offline training demo: completed real XGBoost training,
  exported its bundle and produced an **inconclusive** assessment ending at
  **assessed**, with authorization and deployment both false.
- Installed CLI adapter/public-weights case: initialized successfully; check
  listed all eight missing inputs and refused completion as expected.
- Python compilation, local Markdown links, all 37 registered schema bytes and
  schema manifest replay passed. The governed schema manifest was unchanged.
- `pip check`: no broken requirements found.

Local execution logs and the public teaching run are retained under
`output/pipeline-setup-validation-20260908/`. They are ignored local artifacts,
not guaranteed to be present in a clean clone. The full-suite log is
`unittest.log`; final targeted results are `workflow-tests-final.log`; the
demo entry point is `training-demo/START-HERE.md`.

The installed runtime includes Pydantic 2.13.4, cryptography 49.0.0, NumPy
2.5.3, pandas 3.0.5, SciPy 1.18.1, scikit-learn 1.6.1, XGBoost 2.1.4,
PyArrow 25.0.1 and joblib 1.6.0. These observations identify this local run,
not an independent trusted-runtime attestation. The checkout contained
pre-existing changes; historical reports are not overwritten or restamped.

## Work still required for a government release

No agency-trained model was evaluated, no new fine-tuning or merging study
was run, and no production authority was implemented. Supply real
candidate-specific attacks and applicable ceilings, utility/subgroup results,
security evidence and independent agency review. External identities, isolated
workers, managed signing keys, immutable evidence custody, authoritative
composition/authorization registry and recipient controls remain open in the
[system specification](system-audit-specification.md#industrial-track).

The new commands help collect and check the inputs to those decisions. Their
successful execution cannot close scientific, institutional or operational
obligations by declaration.
