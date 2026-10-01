# Government implementation and academic evidence: execution plan

**Plan date:** 1 October 2026. **Status:** working plan, not a release or an
agency authorization. **Government repository:** `AI_ModeL_Check`.
**Academic destination:** the public `AI_Model_Academic` repository, after its
GitHub remote, visibility and published contents are verified. The local
`AI_Model_Academic` checkout has a README and local evidence inventory, but
its observed `main` has no configured remote; do not describe it as published.

**Local-first checkpoint:** both repository changes are still local. The user
asked to complete local preparation before publishing; P0-14 and P0-15 remain
pending. In this plan, `done` means the stated *local* task is evidenced,
`in_progress` means a reviewable partial result exists, and `pending` means the
task has not met its acceptance criterion. Do not infer a pushed commit from a
local `done` state.

This plan separates the local government teaching and audit implementation from
research manuscripts, experiments and their large evidence stores. It also
produces a source-linked technical advisory report covering *all inventoried
results*, including negative, failed and incomplete work. The report must state
which artifacts are only retained locally and which are independently portable.
No task below permits an agency model release merely because a test or checklist
passes.

## How to execute this plan across short context windows

1. Take one numbered task at a time. Read its dependencies and only the named
   inputs. Record the exact commit/tree and file hashes before editing a
   hash-bound experiment or report.
2. Write a dated receipt with command, runtime, input identities, result,
   skips/failures and output hashes. Use `in_progress` for an incomplete local
   artifact. Change a task to `done` only when its stated evidence exists. Use
   `blocked` with the missing dependency, never a guessed result.
3. Preserve original research files, negative outcomes, failed attempts and
   working-tree changes. Copy or version a frozen artifact instead of silently
   rewriting its bytes. Stage explicit paths for each repository; never run
   `git add .` over the dirty research workspace.
4. Recheck external links, repository visibility and CI after publication.
   A clean local test is not proof that a GitHub reader can reach a source.

Task IDs and states are the handoff interface. The `Depends` column lists
required earlier IDs; a dash means independent. The `Acceptance evidence` column
is the minimum reviewable output, not a claim that it has already been produced.

## Existing boundaries and assets

| ID | State | Verified starting point | Consequence |
| --- | --- | --- | --- |
| B01 | done | The government checkout has a public-data console with ten CPU presets, four bundled datasets, a persistent worker, adversarial screens and a twelve-control review. | Preserve this small local pre-POC as the default setup. |
| B02 | done | The console case workflow and the temporal release broker are separate. The broker needs an initialized, verified registry; a console-trained model is not imported automatically. | An end-to-end release demonstration still needs a bounded bridge or an explicit separate-flow boundary. |
| B03 | done | `docs/publication/2026-09-28/` is a tracked, frozen advisory edition: 51 study sections, 238 tables, 5,543 displayed rows, 104 source references to 94 snapshots, source/hash manifests and a portable verifier. | Preserve this edition and its meanings; displayed rows are not independent experiments. |
| B04 | done | The 28 September edition says its published snapshots can be checked without rerunning the experiments. Original training replay still needs code, data, weights and traces beyond that archive. | Distinguish result verification from full experimental reproduction. |
| B05 | done | The pasted MLSys review audits frozen 21 September ACS artifacts. The local working manuscript is now a different, 30 September draft, *Private Model Export for New Tasks*. | Reconcile old findings by artifact version; do not present them as unverified findings about the new draft. |
| B06 | done | The government-only 22 September publication has retained source-bound test and wheel receipts. Those results apply to that selected tree. | Run current checks again after any implementation changes. |
| B07 | done | A new local `docs/advisory/technical-report-2026-10-01.md` synthesizes the frozen edition, later A1–A28 studies, O1–O7 updates and the pasted review. | Verify its numerical claims and source availability before publication. |
| B08 | done | The government branch has removed its tracked `academic/` tree while the original research workspace retains those files. The independent academic checkout has a committed curated copy and manifest. | Recheck both published trees and links when GitHub access is available. |
| B09 | done | The unchanged frozen publication verifier passes: 123 manifest files, 104 source references, 94 unique sources, 238 tables, 5,543 rows and 148 internal links. | Preserve this dated snapshot unchanged. |
| B10 | done | The final government implementation worktree and a fresh clone of commit `16e23ed` each ran 968 tests (one skipped, no failures). The 37 schemas, frozen verifier and 53-file active link check pass. | Remote CI and external-source reachability remain separate gates. |

## P0 — establish a safe split and a truthful advisory baseline

| ID | State | Depends | Atomic task | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P0-01 | in_progress | — | Capture `HEAD`, branch, remotes, staged/unstaged/untracked lists and dirty-file hashes for the original, government and academic checkouts. | Current branch/status and source commit are known; finish three dated inventories and hashes. |
| P0-02 | pending | P0-01 | Verify the intended public `AI_Model_Academic` GitHub owner, URL, visibility, default branch and credentials after local review. | Recorded remote URL and visible public landing page; no publication claim before then. |
| P0-03 | done | B06 | Establish the local split: preserve the original research workspace, remove the government branch's tracked academic files, and classify selected academic files separately. | The government local branch removes the tracked academic tree; the independent academic `CURATION-MANIFEST.json` records selected/excluded paths. |
| P0-04 | done | P0-03 | Identify local paths, raw data, personal information, credentials, model weights, SQLite stores and oversized binaries before either publication. | Academic curation excludes 22 path-bearing candidates and scans selected/support files; the dated local verification receipt records large aggregate exceptions and the changed government-tree scan. Recheck staged/remote trees at publication. |
| P0-05 | done | B03 | Run the unchanged 28 September `verify_publication.py` without restamping old bytes. | Local verifier passed: 123 manifest files, 104 references, 94 sources, 238 tables, 5,543 rows, 148 internal links. |
| P0-06 | done | P0-03, P0-05 | Retain `docs/publication/2026-09-28/` as the immutable government advisory edition while later academic work is curated separately. | Government README and new advisory distinguish the frozen edition; verifier still passes. Any future relocation needs a separate link map. |
| P0-07 | done | P0-03 | Prepare the academic repository's README, scope map and version policy, including historical 21 September, frozen 28 September and later study series. | README, `artifact-index.md`, `LATER-RESULTS.md` and curation tools are committed in local `826b5e5`; a clean clone explains the publication boundary and passes navigation checks. |
| P0-08 | done | P0-03, P0-04, P0-07 | Copy selected academic work to `AI_Model_Academic` without changing the source; preserve originals and record copied byte hashes. | Local academic commit `826b5e5` contains 438 selected files/31,834,172 bytes; the manifest records original/published SHA-256 for all selected paths and exclusions, while the original workspace remains intact. |
| P0-09 | done | P0-08 | Audit academic links and source references; retain original/published hashes for any normalized copy. | The academic clean clone passes 326 relative links with zero missing, 59 explicitly unbundled references and its canonical index check; original/published hashes remain separate. |
| P0-10 | done | P0-03, P0-06 | Keep government README focused on console setup, supported models, red teaming, audit and synthetic release exercise; label the academic destination as pending. | Local README names the frozen archive and planned academic repository; 51-file active Markdown link check passes. |
| P0-11 | done | P0-03 | Remove academic-only compile/test commands from the government Makefile and update navigation tests without weakening core checks. | Makefile no longer compiles or runs `academic/`; focused audit-navigation tests pass 9/9. Full CI remains P2-06. |
| P0-12 | done | P0-10, P0-11 | Build and install the government wheel outside both repositories. Run console/export discovery and a synthetic action from that wheel. | Final-source isolated temp install imported the wheel package, found both console/export HTML assets, completed prepare/commit/exact-byte download/history verification, and refused a repository lacking retained research receipts; wheel SHA-256 `336495ab7bc1f7a51818e89b9c13fdb803bb95cad7c0b9dddcb907be5b4a545b`. |
| P0-13 | done | P0-03, P0-11 | Replace the machine-specific temporal default with a local optional input path and refuse missing run/operator inputs without creating a registry. | `DEFAULT_ROOT` is `.local/temporal-assurance`; focused launcher tests pass. A separately supplied research workspace must carry the retained ACS verification receipts. |
| P0-14 | pending | P0-02, P0-08, P0-09 | Publish the academic repository only after local review and the user's local-first sequence is complete. | Public commit URL, remote SHA, visibility check and CI status; no claim of completion if blocked. |
| P0-15 | pending | P0-10, P0-11, P0-12, P0-13 | Publish the scoped government implementation/docs only after local review and the user's local-first sequence is complete. | Government commit URL, exact file list, clean-clone checks and CI status; academic drafts excluded. |

**P0 local exit gate:** both trees have explicit purposes, the academic curation
and advisory have source checks, and a clean government checkout runs its own
tests and wheel. P0-14/P0-15 are later publication gates; they stay pending
until the local review is finished. The frozen 28 September edition must keep
passing its original verifier throughout.

## P1 — complete a bounded government workflow and the technical advisory

### Government pipeline, one supported public fixture first

| ID | State | Depends | Atomic task | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P1-01 | pending | P0-12 | Freeze a pilot request: purpose, owner, intended recipient, delivered interface, protected unit/adjacency, dataset version, prior recipient history and utility threshold. | Versioned request and signed-off test plan before outcome inspection. |
| P1-02 | pending | P1-01 | Freeze train/calibration/audit splits, training seeds, mechanism randomness plan, model candidates, attacks, controls and stopping rules. | Hash-bound preregistration; final audit records excluded from selection. |
| P1-03 | pending | P1-02 | Train the supported public fixture and save fitted preprocessing, base/component/derivative lineage, warnings and complete dependency roster. | Reloaded package reproduces predictions; hashes and training runtime recorded. |
| P1-04 | pending | P1-03 | Measure utility against omission, public-only, raw diagnostic and strongest feasible protected baseline under the *same* task requirement and cumulative bound. | Per-arm rows and paired uncertainty; no post-result threshold change. |
| P1-05 | pending | P1-02, P1-03 | Run declared membership, attribute, linkage, extraction or robustness tests only where their tools and recipient interface apply. | Each attack has status, control result, calibration/audit separation, metric, uncertainty and exact model/interface hash. |
| P1-06 | pending | P1-05 | Review exploratory and unsupported attacks separately from decision-bearing ceilings. | Report cannot turn a failed/unsupported attack into a privacy clearance. |
| P1-07 | pending | P1-03 | Bind the candidate, preprocessing, evidence, complete recipient package, parent/ensemble components and earlier copies into a case. | Twelve-control JSON review and stale-evidence behavior for changed bytes. |
| P1-08 | pending | P1-03, P1-07 | Design a narrow import from the supported training fixture to a verified export registry, *only if* the fixture's mechanism and dependencies satisfy that registry's contract. | Import rejects arbitrary console models and every missing channel/unit/roster proof; no invented budget. |
| P1-09 | pending | P1-08 | Execute prepare → checks → local review → atomic commitment → exact-byte download → revocation/restart. | One machine-readable end-to-end receipt matching package, evidence, ledger and delivery hashes. |
| P1-10 | pending | P1-09 | Exercise direct endpoint calls, wrong model, changed artifact, stale review, expired authority/evidence, corrupted ledger and unsupported import. | Every bypass is refused with stable error and no unintended release. |
| P1-11 | pending | P1-09 | Exercise simultaneous commits, interrupted commit/download, idempotent retry, restart and nonrefundable revocation. | Account/receipt conservation and exact-byte replay under every retained trace. |
| P1-12 | pending | P1-07, P1-09 | Connect console and release views by a read-only case/request reference without treating a checklist as authorization. | UI and API display the same stage, outstanding gaps and non-authorizing status. |
| P1-13 | pending | P1-04, P1-05, P1-09 | Generate one reviewer bundle: request, lineage, utility, per-attack results, control states, audit history, receipts, test matrix and limitations. | Manifest verifies every file; internal private caches/SQLite/raw records are absent. |

If P1-08 cannot be justified, mark it `blocked` and retain the educational
console and synthetic export service as two separate demonstrators. Do not make
their screens appear to certify an arbitrary trained model.

### Advisory report and complete result inventory

| ID | State | Depends | Atomic task | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P1-14 | in_progress | P0-05, P0-08 | Build a study ledger for every result in the frozen 28 September edition and every later 29 September–1 October study. Label completed, failed, partial, superseded, exploratory, exact calculation, implementation exercise or hypothetical example. | Local advisory indexes frozen S1–S51, later A1–A28 and O1–O7; complete machine-readable crosswalk and source-hash reconciliation remain. |
| P1-15 | pending | P1-14 | For each study, record dataset and unit, protected scope, model family/arm, N, seeds or worlds, metric, uncertainty, baseline, evaluator, verifier and recipient interface. | Machine-readable rows with no unexplained null or mixed denominator. |
| P1-16 | in_progress | P1-14 | Reconcile the 648 original mixed fits, completed 144 corrected Qwen v2 heads, historical 144 Qwen v1 fits, publication projection and October results against the frozen edition. | Advisory distinguishes the corrected 792-fit total from historical v1 and alternative histories; finish value/source checks. |
| P1-17 | in_progress | P1-14 | Add unfavorable and null results, refused exports, failed attacks, convergence warnings and changed study plans to the ledger. | Advisory already names several negative gates and failures; a systematic coverage check remains. |
| P1-18 | pending | P1-15, P1-17 | Independently recompute every number quoted in the advisory narrative and tables from retained results, or mark source unavailable. | Value-check output includes headline, counterexample and adverse values; no pointer-to-itself verification. |
| P1-19 | in_progress | P1-18 | Reconcile the pasted 21 September review item by item: forest `max_features`, decision-tree record intervals, DIS omission-versus-RR, two-attribute controls, corrected kernel baseline/peak memory, 44k-panel admission, and adaptive privacy statement. | The local advisory has an eight-row disposition table; independent recomputation and per-row source-status labels remain. |
| P1-20 | done | B03, B05 | Draft the source-linked advisory technical report with policy relevance, frozen/later result index, negative findings, review corrections, limits and agency actions. | Local `docs/advisory/technical-report-2026-10-01.md` exists and explicitly calls itself a synthesis; numerical validation remains P1-18/P1-23. |
| P1-21 | in_progress | P1-20 | Check the specific privacy claim for every result: attribute versus membership/whole-record, public fixed fields, recipient history, adaptive selection and release route. | Advisory states general boundaries; per-study claim-to-assumption matrix remains. |
| P1-22 | in_progress | P1-20 | Align the frozen short reader guide and specialist supplement with the later advisory without rewriting the 28 September source archive. | The later displayed-table digest captures 88 tables/737 displayed rows from 26 curated canonical report documents; JSON-only results and complete run archives still require the source index. |
| P1-23 | in_progress | P1-18, P1-20, P1-22 | Verify links, hashes, report text values, table counts and clean-checkout portability. | Both clean clones pass local link/hash/digest checks; the final government implementation and its clean clone pass 968 tests, and all 44 pinned academic citations resolve in the local commit. Complete numeric reconciliation, public URLs and remote CI remain. |

**P1 exit gate:** a tester can follow one bounded supported example from
training to a controlled download or receives a precise refusal; the advisory
report names every inventoried experimental result and its limits. This is
pre-POC evidence, not operational authority.

## P2 — broaden support only where the evidence and owner justify it

| ID | State | Depends | Atomic task | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P2-01 | pending | P1-05, P1-06 | Add recipient-realistic file, linked-score, restricted API, component-joint and adaptive-query tests for model families actually used in a pilot. | Per-interface coverage matrix; unsupported modalities remain visible. |
| P2-02 | pending | P1-03, P1-07 | Add verified fine-tuning, adapter, merge, distillation and ensemble lineage adapters one at a time. | Each derivative has parent/component bytes, overlap, prior access and its own assessment; unsupported trainer stays blocked. |
| P2-03 | pending | P1-21 | Prove or explicitly limit adaptive cumulative privacy claims and account for private model selection, utility labels, linked scores and refusals. | Reviewed mechanism argument and tests bound to the actual release path; no fixed-schedule theorem advertised for arbitrary adaptive choices. |
| P2-04 | pending | P1-11 | Test an external checkpoint/anti-rollback design before claiming protection against privileged database replacement. | Whole-store restore attack is detected by a separately controlled anchor, or the limit stays explicit. |
| P2-05 | pending | P1-12 | Specify identity, role approval, protected storage, key custody, independent reviewer and gateway controls for a real agency deployment. | Named deployment owner and acceptance tests; educational loopback setup remains simple. |
| P2-06 | pending | P1-13, P1-23 | Split CI into government core/E2E, report-verifier, and academic experiment jobs with retained logs and versioned artifacts. | Clean GitHub runs show source SHA, test counts, skips, failed options and published report verifier result. |
| P2-07 | pending | P2-01, P2-03, P2-05 | Run a pilot with one agency-approved dataset and recipient route only after data, authority and threat decisions are supplied by the agency. | Approved data path and separately recorded agency decision; no public sample is relabeled as agency evidence. |

## Unresolved decisions and honest gaps

- **Academic remote:** the local `AI_Model_Academic` checkout has no observed
  remote. Its README and curation checker report 438 selected files,
  326 valid relative links, 59 documented unbundled links and no failures.
  P0-02/P0-07 must establish a reviewable public target before GitHub links
  are presented as live. Publication remains deferred by the local-first request.
- **Frozen archive location:** the 28 September advisory edition is already
  published and hash-bound in the government repository. A complete copy in
  the academic repository may be useful, but moving it first would break links
  and its evidence chain. P0-06 settles the durable location.
- **Later-study completeness:** the 28 September supplement predates the
  648-fit study, completed 144-head corrected Qwen v2 follow-up and October
  work. The local advisory indexes A1–A28 and O1–O7 but is a synthesis, not
  every later numerical row. P1-14/P1-15 must finish the machine-readable
  inventory, including failures and source hashes.
- **Old reviewer scope:** the pasted reject recommendation concerns the 21
  September ACS paper and was not independently rerun by this plan. Later
  corrected kernel and utility reports exist locally, but their provenance,
  portability and current-paper relevance need P1-18 and P1-19 checks.
- **Training-to-broker bridge:** the current console trains ordinary models;
  the temporal broker trusts a separately initialized protected registry. No
  generic import can confer differential privacy or new budget.
- **Security and authority:** current local services assume a trusted operator
  and controlled filesystem. Login, separate approvers, protected custody and
  external anti-rollback are deployment work, not prerequisites for learning
  with bundled public data.
- **Model coverage:** larger vision/LLM training, live RAG/agent behavior,
  audio and diffusion are not universally covered by the local wizard or its
  registered privacy evidence. Unsupported paths must stay explicit.
