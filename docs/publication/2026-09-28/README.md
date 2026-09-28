# Model releases and agency workflows — 28 September 2026

The 19-page reader guide translates the findings into actions for agency staff and policymakers, with a focus on existing planning, procurement, data-access, training, approval, sharing, update and incident workflows. Section 3 follows the current paper. Proposed governance remains scoped to a validation pilot. The successful planning example and complete experimental record are retained.

## Read the guide

- [Accessible guide (Word)](model-risk-v5.docx) · [Guide (Markdown)](guide.md)
- [Complete experimental supplement (Word)](model-risk-experimental-supplement.docx): all 238 tables and 5,543 displayed result rows across 51 study sections. Rows are not independent experiments.
- [Findings to agency actions](findings-to-actions.md): fourteen findings mapped to all 51 study sections.
- [Detailed assessment reference](assessment-reference.md): preserved specialist explanations, numeric examples and glossary.
- [Technical companion](technical-companion.md): detailed assumptions, calculations, protocol context and limitations.
- [Constructive worked example](constructive_example_technical.md) · [exact-arithmetic verifier](verify_constructive_example.py) · [retained results](constructive_example_results.json)

## Inspect the complete reporting evidence

- [Historical model tables](evidence/model_tables.json)
- [Current study tables](evidence/current_tables.json)
- [Auxiliary and historical study tables](evidence/auxiliary_tables.json)
- [Navigable source index, E001–E104 and P1–P10](evidence/source-index.md)
- [Source provenance and normalization manifest](evidence/source-manifest.json)
- [Publication file hashes](publication-manifest.json)
- [Portable publication verifier](verify_publication.py)

The three frozen JSON inputs are byte-identical to the files used for the complete supplement. All 104 original evidence references resolve to 94 distinct source snapshots under `evidence/source/`, preserving the original relative paths and JSON-pointer identities. These are an explicitly bounded reporting archive of public-benchmark and synthetic/finite-study results, certificates, method/coverage records and historical test outcomes. Unfavourable and superseded findings remain identified. Five original context snapshots explain P1–P5. Five additional manuscript snapshots document P6–P10 for the updated workflow; no experimental source or table file was replaced.

## Provenance and reproducibility limits

Original source paths in the guide identify research records; they do not imply every path exists in the repository's main branch. Use the source index and manifest for this edition. Some contextual and historical source documents contain links outside the snapshot. The top-level working manuscript and selected workflow sources are included as context; its full dependency tree is outside this snapshot.

Only local absolute filesystem prefixes in source/context copies were normalized, using placeholders such as `<REPOSITORY>`, `<WORKSPACE>`, `<USER_HOME>` and `<LOCAL_DRIVE_D>`. Numeric JSON tokens, table cells, uncertainty and experimental outcomes were not changed. Original and published SHA-256 hashes and normalization counts are recorded separately. An altered snapshot is not described as byte-identical to its original. The frozen table files and final Word documents are copied unchanged.

This archive supports inspection of all reported model/setting results and their source records. Repeating the original training experiments would also require their code, datasets, model weights and complete traces, which are outside this reporting snapshot. The publication preserves existing results; it does not report new experiment runs or deployment validation.

The worked example is synthetic teaching material. Run `python verify_constructive_example.py` (Python 3.10 or later, standard library only) to reproduce its exact arithmetic; this does not validate deployed random sampling or authorize a release.

Run `python verify_publication.py` to check every published file hash, all 104 source references and JSON pointers, the three frozen table files and internal navigation. It uses the Python standard library and does not rerun experiments. Maintained specification links require the parent repository; historical source/context links are retained as provenance, not advertised as a complete dependency tree.

## Maintained technical references

- [Candidate MRAP protocol and conformance levels](../../model-release-assurance-protocol.md)
- [Mathematical foundations](../../mathematical-foundations.md)
- [Formal verification scope](../../formal-verification.md)
- [Machine-readable schema index](../../../schemas/README.md)

These maintained specifications complement the frozen reporting snapshots. Their conformance levels describe the candidate protocol; wider agency adoption remains a separate decision after validation.
