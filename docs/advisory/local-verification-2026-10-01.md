# Local verification receipt for the government–academic split

**Date:** 1 October 2026. **Scope:** the local government
worktree based on source commit `25f1acf`, and the separate local
`AI_Model_Academic` checkout. These checks do not establish a GitHub release,
an agency deployment, a privacy guarantee for arbitrary models, or complete
experimental retraining.

| Check | Command or method | Observed result |
| --- | --- | --- |
| Government implementation | `python -m unittest discover -s tests -v` with the local pipeline runtime | Final implementation worktree: 968 tests run, one skipped, no failures, 226.200 seconds. A fresh clone of local commit `16e23ed` ran the same 968 tests, one skipped, no failures, in 227.302 seconds. The clone also passed the 37-schema, active-link, frozen-archive and later-table-digest checks. |
| Current schemas | `python scripts/generate_schema_manifest.py --check` | 37 schemas verified; manifest SHA-256 `0c2781f3155990956a71c0ac4c1738007ccb9865885f875b813e5a575cf6ad3b`. |
| Government navigation | `python scripts/check_markdown_links.py` | 53 active Markdown files checked; two generated `output/` links are local-only; 35 preserved publication snapshots are checked by their archive verifier. |
| Frozen 28 September archive | `python docs/publication/2026-09-28/verify_publication.py` | Passed: 123 manifest files, 104 source references to 94 snapshots, 238 tables, 5,543 displayed rows, 148 internal links. |
| Curated academic selection | `python tools/verify_curated.py` in the separate academic checkout | `curated_with_documented_omissions`: 438 selected files/source hashes, 326 valid relative links, zero missing links, 59 explicitly unbundled references, 22 excluded path-bearing candidates, zero failures. Five superseded root notes were removed from the new tree and retained in Git history. |
| Later displayed results | `python scripts/build_advisory_displayed_tables.py --academic-root ../AI_Model_Academic --check` | 26 source-hashed canonical documents across 25 dated families; 88 Markdown tables and 737 displayed data rows. The integrity test rejects a changed source hash and ignores fenced sample tables. |
| Advisory academic citations | Parse the report's pinned `AI_Model_Academic/blob/<commit>/<path>` links and check every Git object at that commit | 44 citations to 39 distinct paths; all 44 point to files in local academic commit `826b5e5fbda2cd50e6bb856a90be1b18619afc11`. The public URL still needs a post-publication check. |
| Isolated wheel smoke | `pip wheel --no-deps --no-build-isolation`, `pip install --no-deps --target` in a temporary directory outside both repositories | Version 0.8.0 wheel SHA-256 `336495ab7bc1f7a51818e89b9c13fdb803bb95cad7c0b9dddcb907be5b4a545b`; import resolved to the temporary install, both console/export HTML assets were present, and console/export help worked. A synthetic first-stage request completed init, prepare, commit, exact-byte download and history verification: 688 downloaded bytes, receipt hash matched, `valid=true`. The installed launcher rejected an explicit repository lacking retained ACS receipts with exit code 2 and created no data directory. |

The full worktree and clean-clone suites include the two advisory-compiler tests
and the research-workspace guard test. The wheel smoke ran against the final
government implementation source, including the explicit research-workspace guard.
The academic verifier checks published bytes and
available original-source hashes, but the full raw experiment archives,
weights and some path-bearing manifests are deliberately absent. The academic
clean clone at commit `826b5e5fbda2cd50e6bb856a90be1b18619afc11` passed
the same 438-file/326-link verifier with no source sibling (zero original-source
hashes available) and regenerated its canonical index without a Git diff.
The government clone passed its active links, 37 schemas, frozen archive
and displayed-table digest checks. Public links, remote commits and live GitHub CI remain tasks in the
[fine-grained plan](../government-academic-separation-plan-2026-10-01.md).

The publication-scope scan found no credentials, raw per-person datasets,
model weights, databases or archives in the selected academic tree or changed
government tree. The 22 source files containing absolute workstation paths are
excluded and named by hash in the academic curation manifest. Three selected
files above 1 MiB are retained aggregate evidence: `paper/experimental-data.json`
(13,878,231 bytes), `paper/independent-model-study-data.json` (4,821,991
bytes, model-level measurements), and a historical clipping-by-world/task CSV
(4,660,852 bytes, aggregate rows). The academic curation tools now use generic
user-path patterns; the verifier scans its support files as well as selected
evidence. The government scan's path hits were test fixtures and public URLs.
This is a current-tree screen, not a claim about every historical Git object.

Publication note (5 October 2026): the workstation branch label was removed
from this copy. The original receipt is retained locally and in Git history.
