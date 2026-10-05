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
task has not met its acceptance criterion. `retired` identifies a former
requirement explicitly superseded by the user. Do not infer a pushed commit
from a local `done` state.

This plan separates the local government teaching and audit implementation from
research manuscripts, experiments and their large evidence stores. It also
produces a source-linked technical advisory report covering *all inventoried
results*, including negative, failed and incomplete work. The report must state
which artifacts are only retained locally and which are independently portable.
No task below permits an agency model release merely because a test or checklist
passes.

## Retired 28 September archive

On 1 October 2026 the user requested removal of the dated frozen advisory
archive from this government checkout. That request supersedes the earlier
retention requirement in B03/P0-06. The 123 files under
`docs/publication/2026-09-28/` (47,179,965 bytes) were removed from the working
tree. They remain recoverable in local Git commit
`0b9958954f30134e9662d0797bd465df26051806`; Git history was not rewritten.

That historical edition contained 51 study sections, 238 tables and 5,543
displayed rows, with 104 evidence references to 94 source snapshots. It did not
include all original training data, model weights or complete traces, and did
not cover studies completed after that date. The later technical advisory and
displayed-table digest remain in the current checkout.

To inspect the retired overview or finding-to-action map without restoring the
archive into the active checkout, run these read-only commands from this repo:

```bash
git show 0b99589:docs/publication/2026-09-28/README.md
git show 0b99589:docs/publication/2026-09-28/findings-to-actions.md
```

The source index, source/hash manifests, Word documents, tables and verifier
are under the same historical Git directory. Replaying its verifier requires
a separate checkout of that commit. The dated local verification receipt and
completed checks below record pre-retirement results, not a claim that the
archive still exists or is verified by the current test run. Any remaining
task that needs the retired evidence must explicitly retrieve that version
from history. Current navigation checks validate the remaining documents.
The original research workspace and separate academic repository are unchanged;
GitHub publication is still pending authentication.

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
| B03 | retired | The 28 September edition recorded 51 study sections, 238 tables, 5,543 displayed rows, 104 source references to 94 snapshots, manifests and a verifier. Its 123 files were removed at the user's request. | Retrieve the historical edition from commit `0b99589` when needed; displayed rows are not independent experiments. |
| B04 | done | The 28 September edition says its published snapshots can be checked without rerunning the experiments. Original training replay still needs code, data, weights and traces beyond that archive. | Distinguish result verification from full experimental reproduction. |
| B05 | done | The pasted MLSys review audits frozen 21 September ACS artifacts. The local working manuscript is now a different, 30 September draft, *Private Model Export for New Tasks*. | Reconcile old findings by artifact version; do not present them as unverified findings about the new draft. |
| B06 | done | The government-only 22 September publication has retained source-bound test and wheel receipts. Those results apply to that selected tree. | Run current checks again after any implementation changes. |
| B07 | done | A new local `docs/advisory/technical-report-2026-10-01.md` synthesizes the frozen edition, later A1–A28 studies, O1–O7 updates and the pasted review. | Verify its numerical claims and source availability before publication. |
| B08 | done | The government branch has removed its tracked `academic/` tree while the original research workspace retains those files. The independent academic checkout has a committed curated copy and manifest. | Recheck both published trees and links when GitHub access is available. |
| B09 | done | Before retirement, the unchanged publication verifier passed: 123 manifest files, 104 source references, 94 unique sources, 238 tables, 5,543 rows and 148 internal links. | Historical verification only; the archive and verifier are no longer current-checkout inputs. |
| B10 | done | The final government implementation worktree and a fresh clone of commit `16e23ed` each ran 968 tests (one skipped, no failures). The 37 schemas, frozen verifier and 53-file active link check pass. | Remote CI and external-source reachability remain separate gates. |

## P0 — establish a safe split and a truthful advisory baseline

| ID | State | Depends | Atomic task | Acceptance evidence |
| --- | --- | --- | --- | --- |
| P0-01 | in_progress | — | Capture `HEAD`, branch, remotes, staged/unstaged/untracked lists and dirty-file hashes for the original, government and academic checkouts. | Current branch/status and source commit are known; finish three dated inventories and hashes. |
| P0-02 | pending | P0-01 | Verify the intended public `AI_Model_Academic` GitHub owner, URL, visibility, default branch and credentials after local review. | Recorded remote URL and visible public landing page; no publication claim before then. |
| P0-03 | done | B06 | Establish the local split: preserve the original research workspace, remove the government branch's tracked academic files, and classify selected academic files separately. | The government local branch removes the tracked academic tree; the independent academic `CURATION-MANIFEST.json` records selected/excluded paths. |
| P0-04 | done | P0-03 | Identify local paths, raw data, personal information, credentials, model weights, SQLite stores and oversized binaries before either publication. | Academic curation excludes 22 path-bearing candidates and scans selected/support files; the dated local verification receipt records large aggregate exceptions and the changed government-tree scan. Recheck staged/remote trees at publication. |
| P0-05 | done | B03 | Run the unchanged 28 September `verify_publication.py` without restamping old bytes. | Local verifier passed: 123 manifest files, 104 references, 94 sources, 238 tables, 5,543 rows, 148 internal links. |
| P0-06 | retired | P0-03, P0-05 | Former requirement to retain `docs/publication/2026-09-28/` in the government checkout; superseded by the user's archive-removal request. | Files remain in Git history at `0b99589`; active links point to the retirement and recovery note. |
| P0-07 | done | P0-03 | Prepare the academic repository's README, scope map and version policy, including historical 21 September, frozen 28 September and later study series. | README, `artifact-index.md`, `LATER-RESULTS.md` and curation tools are committed in local `826b5e5`; a clean clone explains the publication boundary and passes navigation checks. |
| P0-08 | done | P0-03, P0-04, P0-07 | Copy selected academic work to `AI_Model_Academic` without changing the source; preserve originals and record copied byte hashes. | Local academic commit `826b5e5` contains 438 selected files/31,834,172 bytes; the manifest records original/published SHA-256 for all selected paths and exclusions, while the original workspace remains intact. |
| P0-09 | done | P0-08 | Audit academic links and source references; retain original/published hashes for any normalized copy. | The academic clean clone passes 326 relative links with zero missing, 59 explicitly unbundled references and its canonical index check; original/published hashes remain separate. |
| P0-10 | done | P0-03, P0-06 | Keep government README focused on console setup, supported models, red teaming, audit and synthetic release exercise; label the academic destination as pending. | README identifies the retired archive and its Git recovery point alongside the later advisory and planned academic repository. |
| P0-11 | done | P0-03 | Remove academic-only compile/test commands from the government Makefile and update navigation tests without weakening core checks. | Makefile no longer compiles or runs `academic/`; focused audit-navigation tests pass 9/9. Full CI remains P2-06. |
| P0-12 | done | P0-10, P0-11 | Build and install the government wheel outside both repositories. Run console/export discovery and a synthetic action from that wheel. | Final-source isolated temp install imported the wheel package, found both console/export HTML assets, completed prepare/commit/exact-byte download/history verification, and refused a repository lacking retained research receipts; wheel SHA-256 `336495ab7bc1f7a51818e89b9c13fdb803bb95cad7c0b9dddcb907be5b4a545b`. |
| P0-13 | done | P0-03, P0-11 | Replace the machine-specific temporal default with a local optional input path and refuse missing run/operator inputs without creating a registry. | `DEFAULT_ROOT` is `.local/temporal-assurance`; focused launcher tests pass. A separately supplied research workspace must carry the retained ACS verification receipts. |
| P0-14 | pending | P0-02, P0-08, P0-09 | Publish the academic repository only after local review and the user's local-first sequence is complete. | Public commit URL, remote SHA, visibility check and CI status; no claim of completion if blocked. |
| P0-15 | pending | P0-10, P0-11, P0-12, P0-13 | Publish the scoped government implementation/docs only after local review and the user's local-first sequence is complete. | Government commit URL, exact file list, clean-clone checks and CI status; academic drafts excluded. |

**P0 local exit gate:** both trees have explicit purposes, the academic curation
and advisory have source checks, and a clean government checkout runs its own
tests and wheel. P0-14/P0-15 are later publication gates; they stay pending
until the local review is finished. After archive retirement, current checks
cover the remaining government tree; any historical archive replay must use
its preserved Git version and original verifier in a separate checkout.

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

### Implemented partial milestone: local red-team export screening

The [red-team export pilot and gate](red-team-export-review.md) now provide
unified tool discovery, a frozen public GaussianNB membership-screen plan,
exact-package reload, known-leak/null controls, policy/report validation,
report attachment and repeated temporal HTTP enforcement. Default screening
blocks missing policy/report, stale evidence, unsupported or failed tools,
identity mismatches, bad controls and threshold violations. A report change
invalidates prior checks and review; expiry can block delivery after commitment.

This advances parts of P1-02/P1-03/P1-05/P1-06/P1-10/P1-13, but does not complete
the acceptance gates above. The pilot has one public fixture and one attack,
no agency-approved request, protected-training import, private-data registry,
complete utility comparison, full-interface privacy bound or unified private
release receipt. P1-08/P1-09/P1-12 and the wider P2 work remain pending. The
explicit legacy teaching mode is visibly unassessed. External attack-framework
adapters and isolated authenticated workers remain future work.

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
| P1-22 | in_progress | P1-20 | Reconcile the historical short reader guide and specialist supplement with the later advisory using the retired edition from Git history. | The later displayed-table digest captures 88 tables/737 displayed rows from 26 curated canonical report documents; complete reconciliation still requires retrieval of the historical sources. |
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

## Production delivery workstream

The user selected **agency private cloud** for production planning. The
[production plan](production-private-cloud-plan.md) expands deployment work into
PRD-01–PRD-27 with owners, dependencies, acceptance evidence and operational
gates. It preserves the scientific and accounting requirements above. These are
planned tasks, not completed infrastructure or permission to release agency
models. The first sprint establishes scope, threat model, source/CI baseline and
cloud decisions; wider model support needs separate acceptance.
[PRD-01 scope and ownership](production-prd01-scope-and-ownership.md) and
[PRD-02 threat model and cloud decisions](production-prd02-threat-model.md) are
now drafted and remain in progress pending accountable agency decisions. The
user selected major public-health agency scope and has left provider and region
open; no cloud deployment or private-data admission is authorized by the drafts.
[PRD-03](production-prd03-source-build-baseline.md) now records local source/build
verification while publication and protected release configuration remain pending.
[PRD-04](production-prd04-required-ci.md) adds a required no-skip government CI
profile and Windows/Ubuntu package/release dependencies; remote execution and
required-check configuration remain pending authentication.
[PRD-05](production-prd05-infrastructure-scaffold.md) adds a strict provider-neutral
environment blueprint and local public-fixture API/worker lifecycle rehearsal.
The blueprint stays non-deployable; provider infrastructure and cloud control
acceptance remain pending the deferred decisions and agency review.
[PRD-06](production-prd06-identity-and-approvals.md) adds a separate signed-token,
case-permission and independent-approval fixture with current-role/revocation
checks. It remains non-authorizing; live SSO/MFA and production enforcement are
not implemented by protecting this isolated test surface.
[PRD-07](production-prd07-governed-storage.md) adds a separate public-only storage
fixture: exact immutable references, bounded worker reads, expiring/revocable
grants and nondestructive retention/hold decisions. Cloud custody, private
intake, large-data queries and durable grant state remain unimplemented.
[PRD-08](production-prd08-key-trust.md) adds current access-token key trust and
a memory-only signer behind a provider interface. Revocation also affects
saved reviews and storage grants. Agency managed custody, authenticated durable
key administration and other key purposes remain pending.
[PRD-09](production-prd09-build-controls.md) adds complete public-fixture wheel
locks, SBOM/license evidence, current advisory checks and source-bound signed
local build evidence. Known-advisory pins were patched; production licensing,
images, protected builders and independently trusted admission remain pending.
[PRD-10](production-prd10-durable-jobs.md) adds a separate fixed-public-input job
workflow with durable leases and consumed-grant history, current identity/key
checks and controlled child-process cleanup. Broker restart cannot reconstruct
process-local storage or authority. Private-cloud isolation, durable agency
recovery and production image admission remain pending.
[PRD-11](production-prd11-adapter-benchmarks.md) broadens the framework beyond
healthcare at the user's request. It adds typed numeric adapters, inert candidate
replay and bounded checks of available public research corpora on D:. Historical
source availability, registered-only datasets and completed model tests are
reported separately; full-corpus reproduction and production acceptance remain open.
[PRD-12](production-prd12-authenticated-evidence.md) adds signed local replay
evidence with current trust, exact artifact/context bindings and durable one-use
challenges. Unavailable image/isolation guarantees deny production admission;
agency custody and production job/release integration remain open.
[PRD-13](production-prd13-model-registration.md) adds prospective registration
before fitting eight pinned public profiles, with exact source/sample lineage,
population and non-DP limitations, a frozen descriptive utility comparison and
local registration/disclosure history. Arbitrary model import is refused and
external disclosure history remains unknown. Agency/scientific qualification
and cumulative privacy accounting remain open; no candidate is cleared.
[PRD-14](production-prd14-sacro-adapter.md) adds the pinned external SACRO-ML
probability-membership adapter in a separate runtime, with frozen controls and
independent score/count replay. All eight profiles receive a disposition; seven
classifiers are applicable and Diabetes regression is unsupported. This local
milestone remains in progress for agency scientific/security/license acceptance
and cannot clear a model or establish platform isolation. The
[PRD-15 continuation](production-prd15-registry-transactions.md) adds local atomic
registry/migration/outbox checks. Next is **PRD-16**, independent witness and recovery.

## Unresolved decisions and honest gaps

- **Academic remote:** the local `AI_Model_Academic` checkout has no observed
  remote. Its README and curation checker report 438 selected files,
  326 valid relative links, 59 documented unbundled links and no failures.
  P0-02/P0-07 must establish a reviewable public target before GitHub links
  are presented as live. Publication remains deferred by the local-first request.
- **Retired archive:** the 28 September edition was removed from this checkout
  at the user's request. Its last retained version is in Git commit `0b99589`;
  P0-06 is retired. Follow the recovery note above for historical evidence and
  do not describe old verifier receipts as current-checkout verification.
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

## 2 October production continuation

[PRD-15](production-prd15-registry-transactions.md) implements a separate bounded
local registry with atomic heads, fictional charges, immutable receipts and
outbox, explicit version migration and current signed identity/storage guards.
Process race/crash, retry and local receiver deduplication checks preserve the
engineering invariants. Previous source and evidence remain intact; no research
workspace was modified. Real privacy accounting, PostgreSQL/cloud failover and
agency acceptance remain pending. Next is PRD-16, independent witness and
intent/event recovery. Publication still requires GitHub authentication.

## PRD-16 local continuation

[PRD-16](production-prd16-witness-recovery.md) adds a separate bounded witness
with complete registry events, irreversible pre-commit intents and external
checkpoint floors covering its own log. Rollback/fork, missing-intent, stale/new
ledger, process-crash and uncertain-commit recovery checks preserve prior charges.
Physical independent agency custody and signed remote witness/restore acceptance
remain pending. All earlier implementation/evidence is preserved. Next is PRD-17,
policy-authority approval and independent review; GitHub authentication is pending.

## PRD-17 local continuation

[PRD-17](production-prd17-policy-review.md) binds current signed policy approval
before prospective registered public training and exact authenticated replay,
with distinct canonical assessors/release reviewers, scoped delegation and
retained policy/outcome history. Post-result weakening and evidence reuse are
rejected. All earlier implementation and evidence remain preserved on D:.
Agency authority, scientific qualification and witnessed approval custody remain
pending. Next is PRD-18 controlled delivery; GitHub authentication is pending.

## PRD-18 local continuation

[PRD-18](production-prd18-controlled-delivery.md) adds a current human-recipient
gateway for exact public-fixture candidate bytes, with activation/grants, fresh
per-chunk admissions, suspension/revocation and retained own-log checkpoint
floors. Production delivery is refused by default. Earlier implementation and
evidence remain preserved on D:. Protected agency/cloud routes, independent
witness custody and scientific qualification remain pending. Next is PRD-19,
one profile end to end; GitHub authentication is pending.

## PRD-19 local continuation

[PRD-19](production-prd19-end-to-end-profile.md) connects a fresh public Wine
profile through a prefit combined native/SACRO plan, independent bound review,
atomic fixture activation, exact delivery/lifecycle and signed historical receipt.
Native-only approval cannot open this facade. Current evidence expires normally
during external work; replay grants no live permissions. Earlier implementation
and evidence remain preserved. Production qualification and GitHub authentication
remain pending. Next is PRD-20, monitoring and incidents.

## PRD-20 local continuation

[PRD-20](production-prd20-monitoring-incidents.md) adds metadata-only fault
monitoring with durable atomic event/incident/alert history, retained checkpoint
floors, a deduplicating local receiver and current-authority incident handling.
Rehearsals inject worker, key, public-data and witness/ledger faults. Existing
implementation and evidence remain preserved on D:. Actual agency telemetry,
independent custody and operational response acceptance remain pending.
Next is PRD-21, scale and recovery qualification; GitHub authentication is pending.

## PRD-21 local continuation

[PRD-21](production-prd21-capacity-recovery.md) measures bounded synthetic
public-data I/O and real fixture-job concurrency, verifies witnessed historical
backup/restore with exact retained anchors and tests lost live delivery contexts
after component restart. Historical receipts/counters stay distinct from current
release authority and real privacy budgets. Agency-approved workload targets,
cloud failover and independent restore qualification remain pending. Earlier
source and evidence stay preserved on D:. Next is PRD-22, independent security
and evidence assessment; GitHub authentication is pending.

## PRD-22 local continuation

[PRD-22](production-prd22-independent-assessment.md) adds fixed fresh public-native
adversarial probes, a signed externally pinned historical assessment packet and
current independent local finding review. Eleven production blockers stay open;
local residual acknowledgments cannot authorize deployment. Earlier source and
evidence stay preserved on D:. Appointed agency security/scientific assessment
and GitHub authentication remain pending. Next is PRD-23, the restricted pilot plan.

## PRD-23 local continuation

[PRD-23](production-prd23-restricted-pilot.md) adds an exact public-evidence pilot
plan with seven current signed fixture people, independent plan acknowledgment,
scoped suspension/resume and terminal withdrawal. Eleven production blockers
remain open; historical packets/records cannot restore admission. Earlier work
and evidence remain preserved on D:. Agency pilot acceptance and GitHub
authentication are pending. Next is PRD-24, exit review and operational handover.
