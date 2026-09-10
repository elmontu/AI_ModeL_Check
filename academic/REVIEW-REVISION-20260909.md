# Review revision — September 9, 2026

The defensible thesis is now an evidence-admission and invalidation contract
that integrates established privacy and assurance-case methods with proposed
government lifecycle decisions. The revision does not establish a novel privacy
measure, empirical governance effectiveness or a production authorization system.

The [canonical manuscript](paper/mra-paper.tex) incorporates the changes.
Its [new appendix](paper/revision-boundaries.tex) contains the closest-work
comparison, conditional Canadian government walkthrough, claim-to-evidence
matrix and prospective validation plan.

| Review issue | Implemented correction | Boundary that remains |
|---|---|---|
| Prior-only strategy missing from absolute floors | Finite-channel analyzer and central decision reducer include the bound prior-optimal guessing strategy; exact comparisons and downward display rounding are tested. Incremental metrics retain baseline zero. | Arbitrary unbound priors are not inferred from free text or maximum-prior caps. Historical raw floors are preserved. |
| Optional risks bypassed by a mandatory-only overall verdict | Selection, joint portfolio coverage and transfer checks now cover every in-scope threat. | The implemented subset requires all cells to CLEAR. Policy-permitted optional RWR selection is refused until its acceptance/transfer path is implemented. |
| Revoked disclosures omitted from composition | Snapshot 1.1 separates cumulative `disclosed_release_ids` from active service. Portfolio evidence must cover cumulative history plus the candidate. Legacy snapshots cannot optimize. | Complete history, cross-domain continuity and a monotone authoritative registry remain external premises. The schema alone cannot establish them. |
| Generic recollection advice treated as actionability | Outward unaccepted crossings now BLOCK because the current implementation lacks a resolving-plan verifier. Advisory suggestions remain in the internal assessment. Otherwise complete crossings can still receive explicitly signed, exactly bound acceptance. | INCONCLUSIVE is reserved until a verifier establishes procedure, estimand, available data, fresh allocation and a decision-changing target. No other blocking condition can be waived. |
| Overstated novelty and government relevance | Added Alvim et al., PRAISE and Powell–Oswald comparisons; narrowed abstract and contribution claim; added a dated, conditional Canadian profile and continued redress/service-continuity duties. | The profile has no actual departmental approval, completed impact determination, participant study or field validation. |
| Historical outcomes confused with corrected implementation | Distinguished retained analyzer CLEAR/HOLD frequencies from the current facade and optimizer; added a separately named current synthetic example. | No historical experiment, failed result, proof receipt or original assessment report was rewritten as new evidence. |

The existing synthetic example and its digest-pinned demo inventory were updated
to use the new snapshot contract and a newly generated
[assessment example](../examples/evidence/assessment-clear-report-review-20260909.json).
The old `examples/evidence/assessment-clear-report.json` is retained; its
decision reduction is incompatible with the corrected reducer. This is a fresh
evaluation of an explicitly synthetic fixture, not new model training.

## Verification

The [consolidated receipt](../output/review-revision-20260909/checks-20260909T104027.166600Z/results.json)
records **212 tests considered: 208 passed, four skipped, no failures or errors**.
The four skipped tests require SciPy, absent from the existing runtime. They
cover exact portfolio optimization and related CLI flows; those checks remain
unverified here. No dependencies were installed. This is a targeted suite,
not a claim that every repository test passed.

The checks include the new counterexamples, finite-channel decisions, real
synthetic evidence-to-signed-acceptance replay, optimizer, CLI, audit, schemas,
synthetic government demo and academic artifact tests. All **109 historical
source digests match** the unchanged companion. TeX input, reference, citation
and environment consistency checks passed. A TeX compiler was not available
on PATH; no new PDF layout or bibliography rendering is claimed. Lean was not
rerun, and the new invariants are not attributed to historical proof receipts.

Reproduce these checks with an existing compatible Python environment:

```powershell
python academic/scripts/verify_review_revision.py
```

The checker creates a new timestamped receipt directory on every invocation.
The earlier consolidated harness attempt is retained: it had four CLI failures
because child processes lacked the source-package path; the harness was fixed
to propagate it. Earlier exploratory runs also exposed the stale example
reports and assertions, and the missing optional solver dependency. Those
observations were used to correct the current fixtures and scope the checks.

The [source availability inventory](paper/source-availability-review-20260909.json)
records local access and Git tracking separately from independently verified
public availability. [Literature notes](paper/review-literature-notes.json)
record primary sources and limits. The direct Canadian Directive page returned
“Request Rejected”; the walkthrough relies on accessible official guidance
and makes no exhaustive clause-level compliance claim.

Pre-edit copies are under `output/review-revision-20260909/before/`.
The revision's change manifest and isolated diff use those copies, rather than
mistaking unrelated pre-existing working-tree changes for this revision.

## Remaining publication conditions

The manuscript remains an extended protocol/integration draft. These changes
remove concrete unsafe promotions and unsupported implications; they cannot
create missing scientific or institutional evidence.

1. **Confirmatory empirical work:** preregister independent model replications,
   unsafe and boundary controls, disjoint utility measurement, and a corrected
   end-to-end comparison under equal evidence/error budgets. Preserve failed
   candidates and distinguish model-level variation from analyzer resampling.
2. **Theory and systems work for broader claims:** implement and verify the
   resolving-plan and optional-RWR selection routes; provide a real cumulative
   registry and gateway if claiming lifecycle enforcement, with crash, race,
   rollback, expiry and revoked-disclosure tests. Written premises and Python
   regressions are not a refinement proof.
3. **Governmental and submission work:** obtain competent review of one actual
   jurisdiction/service profile, resolve ethics/waiver and human-authorship
   responsibilities, evaluate review and redress with appropriate participants,
   and package accessible evidence. Missing original weights and absent field
   outcomes cannot be repaired by wording or fresh hashes.
