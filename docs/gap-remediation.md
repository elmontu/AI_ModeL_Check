# Gap remediation and migration — 0.8.0

Status: reference implementation and operating guide. This is a local enforcement
revision, not an accreditation, new empirical privacy study, or claim that every
deployment and proof obligation is solved.

## What changed

| Boundary | Implemented correction | Remaining premise |
|---|---|---|
| Imported assessments | Report 6.0 checks exact/display bounds, reduction, nonempty decisions, evidence/battery consistency; signing and optimization replay original request and active policy | Authentic inputs and independent execution |
| Source-file races | Clearance-critical engine, optimizer and portfolio JSON imports hash and parse the same captured bytes | This is not immutable storage or a guarantee about a later served artifact |
| Policy laundering | Imports bind roster, mandatory flags, metric/game, thresholds, producer rules and battery requirements | Legitimacy of the externally supplied policy authority |
| Optimizer arithmetic | Rational replay of finite channels, priors and garbling; exact threshold comparisons and outward display values | Full Python refinement, whole-program numeric proof and truthful joint channels |
| Lifecycle signatures | Run 1.2 / authenticated_v2 bind full run context, including every population scope | Trusted keys, authenticated roles and externally enforced separation of duties |
| Lifecycle sequencing | Future events rejected; typed assessment/optimization payloads parsed, cross-bound and checked at recording and downstream consumption, including before a terminal event; transition/predecessor constraints remain enforced | Arbitrary governance blobs are still declarations, not verified production receipts |
| Local audit | Verify existing prefix while holding the append transaction; refuse continuation of corrupted history | External anchors, immutable retention and rollback detection outside SQLite |
| Governance verdict | Separate exact-bound four-verdict record and signed semantic-replay gate; missing evidence is BLOCK | Acceptance authority is externally configured; recommendation is not deployment |
| Taxonomy | Exact finite declared-scenario partition with exclusions, channel witnesses, and request-bound attacker context | Truth and world completeness of the approved adversary universe |
| Experiment integrity | Frozen studies retain source hashes; changed code makes old registrations fail closed | Fresh prospective registration and execution for new performance claims |
| Schema ambiguity | Only current registered schema files remain active | Retained vintage runtime needed to replay historical contracts |

Assessment and optimizer reports retain their existing lower-level terminology.
The new decision-maker-facing record does not silently reinterpret an old signed
report or relabel a failed gate as residual-risk acceptance.

The prior counterproof package remains a baseline, not a current pass certificate.
Its main local closure groups map to these executable regressions:

| Prior finding | Current rejection/control evidence |
|---|---|
| H1/H2/H8: policy, battery and report laundering | [Contract regressions](../tests/test_counterproof_contract_regressions.py), [optimizer regressions](../tests/test_counterproof_optimizer_regressions.py) |
| H3: understated numeric ceiling | [Exact optimizer boundary regressions](../tests/test_counterproof_optimizer_regressions.py) |
| H4/H5/H9: unsigned context, noncausal time, corrupted-prefix append | [Lifecycle and audit regressions](../tests/test_counterproof_lifecycle_regressions.py) |
| H6: typed payload assertions | [Lifecycle report replay](../tests/test_counterproof_lifecycle_regressions.py); execution truth remains external |
| H10/H11: verdict and declared-scope semantics | [Assurance record regressions](../tests/test_assurance_record.py), [fresh sampled crossing integration](../tests/test_assurance_crossing_integration.py); world coverage remains unproved |
| Additional source-swap race | [Engine/provenance snapshot regressions](../tests/test_verified_source_reads.py), [portfolio source snapshot regressions](../tests/test_counterproof_portfolio_source_reads.py) and optimizer source-import mutations |

H7's authoritative live inventory/atomic commit/anchored-retention obligations are
not closed by these tests. Mathematical countermodels continue to refute any
stronger claim that discards the statistical, scope or deployment premises.

## Four-verdict record and gate

For each requested threat, the record contains the canonical game hash and metric,
exact rational `floor`, `ceiling`, `gap`, `threshold`, evidence identifiers,
whether the decision crosses the gap, and fields reserved for a verified
applicable resolving action. Internal analyzer suggestions remain advisory.
Bounds refer to the **declared game metric**. A success probability must not be
called adversary advantage without an explicit baseline/game transformation.
Empirical confidence floors are not deterministic population lower bounds.

The equality convention is explicit: a ceiling equal to its threshold satisfies
the threshold; a floor must be strictly greater to demonstrate a violation.

| Verdict | Necessary conditions |
|---|---|
| RELEASE | Every threat has admissible evidence, no unresolved required obligation, and ceiling <= threshold; its assessment permits clearance |
| RELEASE-WITH-RISK | No blocking condition or floor violation; some floor <= threshold < ceiling; approved scope permits acceptance; a trusted, current, context-bound signature accepts **every** crossing threat's exact ceiling |
| BLOCK | Missing/malformed/stale evidence, failed mandatory obligations, contradictions, demonstrated floor > threshold, invalid signature/context, or no permitted disposition |
| INCONCLUSIVE | Normatively requires complete admissible evidence and a verified applicable resolving plan; current builder does not emit it |

In the absence of acceptance, the current builder blocks a complete crossing
because it cannot verify an actionable resolver. A decision-maker may explicitly
accept the remaining risk under permitted policy. Only a record whose sole
blocking reason is the missing verified resolving plan is eligible for this
signature helper; replay still checks all evidence, scope, trust, time and exact
ceilings. No other blocking condition can be waived. Even accepted ceilings are
upper bounds, not estimates of realized harm.

## September 9, 2026 review revision

This is a working-tree correction after the retained 0.8.0 evidence; it is not a
newly validated production release. Pre-edit files and fresh check receipts are
kept separately under `output/review-revision-20260909/`.

- Absolute finite exact-guess floors include the bound prior-optimal strategy;
  equal-prior membership has baseline 1/2. Incremental metrics have baseline zero.
  A maximum-prior cap is not an attained baseline. Exact fractions drive the
  decision and displayed baseline floors round downward.
- Optimizer feasibility, joint portfolio evidence and transfer bindings cover
  **every** in-scope threat. The supported subset requires every cell to CLEAR.
  The mandatory-only overall assessment verdict cannot bypass an optional
  crossing or blocking floor. Integrating policy-permitted optional RWR through
  selection and transfer remains future work, and those candidates are refused.
- `PortfolioRegistrySnapshot` 1.1 adds `disclosed_release_ids`, the conservative
  cumulative roster. Active identifiers must be included in it; portfolio
  evidence must cover this roster plus the candidate. Empty active service does
  not mean empty disclosure history. Legacy 1.0 snapshots remain inspectable
  but fail optimization. Fresh synthetic examples use an explicitly empty
  cumulative roster; historical evidence has not been migrated or restamped.
- A recognized analyzer action code is insufficient for outward INCONCLUSIVE.
  A future plan verifier must bind the estimand, procedure, instance, available
  data, unspent allocation and a justified decision-changing target. The current
  facade refuses that route; it retains internal scientific suggestions without
  treating them as verified plans.

The supplied roster's completeness and persistence remain external registry
obligations. This schema correction does not implement a monotone log, prevent
rollback, or prove that two composition domains have independent adversaries.
The manuscript specifies those invariants and service-continuity and
post-retirement redress duties; the CLI does not enforce governmental duties.

The [new regression checks](../tests/test_review_revision_regressions.py) cover
the concrete counterexamples. The [manuscript revision appendix](../academic/paper/revision-boundaries.tex)
provides the closest-work comparison, conditional Canadian profile walkthrough,
claim-to-evidence matrix and prospective studies. No independent model training,
government participant study or new Lean refinement is claimed.

The approved scope enumerates a finite scenario universe; every scenario has
exactly one threat owner or a reasoned exclusion. Every exported channel/threat
mapping has an assigned scenario witness. Access, query budget and adaptivity
match the request exactly. Auxiliary knowledge and metadata profiles are bound
**per threat** rather than merged into a stronger attacker without new evidence.
The supported channel inventory and export flags match the typed interface
exactly; extra channels are not silently certified. Free-text descriptions are
explanatory declarations, not independently verified premises.

After an externally reviewed scope has been created against
`assurance-scope-v1.json`, the command sequence is:

```bash
mra assurance-record examples/request.json output/assessments/demo-report.json \
  --scope approved-scope.json --output output/assurance-record.json
mra assurance-sign output/assurance-record.json \
  --private-key assessor-private.pem --output output/signed-assurance-record.json
mra assurance-gate output/signed-assurance-record.json \
  --request examples/request.json --report output/assessments/demo-report.json \
  --scope approved-scope.json --trust-store assessor-trust.json \
  --output output/assurance-gate.json
```

Trust stores are JSON mappings from signer key identifier to public PEM path;
relative paths resolve against the trust-store file. A key supplied inside an
untrusted artifact is not a trust root. Private keys are not example artifacts.

For an actionable crossing record, an authorized reviewer can run
`assurance-accept-risk RECORD --private-key KEY --reason REASON --expires-at TIME
--output ACCEPTANCE`. Rebuild with `assurance-record ... --acceptance ACCEPTANCE
--acceptor-trust-store TRUST`, then sign and gate with the same acceptor trust
store. Acceptance is not automatically produced by assessment. Production key
custody and identity authorization are external responsibilities.

The gate consumes the signed record, verifies the signature against its supplied
trust store, replays the complete disposition at creation time, compares exact
canonical bytes, and rechecks current freshness. Missing inputs, malformed
contracts and verification errors produce a machine-readable BLOCK and a
nonzero exit status. INCONCLUSIVE also does not pass. A successful result sets
`recommendation_passed=true` but **always** `authorization_eligible=false`.
These new file-based commands do not establish an AuditStore-linked durable
workflow; production orchestration must record and enforce their handoffs.

## Conditional correctness arguments

These are mathematical arguments about the stated semantics, not a claim of new
machine-checked Python refinement. The existing Lean model remains a separate,
scoped protocol abstraction.

1. **Interval decision soundness.** Let R_T be the actual risk in the same
   declared game and assume all admitted bounds simultaneously satisfy
   L_T <= R_T <= U_T. If RELEASE is returned, for every T the gate checks
   U_T <= tau_T. Transitivity gives R_T <= tau_T. If L_T > tau_T, transitivity
   gives R_T > tau_T, so BLOCK is warranted. If L_T <= tau_T < U_T, the interval
   alone supports both possibilities; neither universal safety nor a violation
   follows. Signed acceptance is a governance decision, not a safety theorem.
2. **Confidence qualification.** For statistically valid bounds with per-family
   failure budgets alpha_i, the union bound gives simultaneous validity at least
   1 - sum(alpha_i), when those budgets cover the actual selection/stopping
   procedure. The record does not invent a global confidence guarantee by
   multiplying or ignoring heterogeneous report confidences. Cross-threat and
   lifetime statistical error accounting remains an explicit external proof
   obligation unless supplied by the approved evidence plan.
3. **Scope inclusion, relative not universal.** Let D be the approved finite
   declared scenario set, S_T its disjoint threat-owned cells, and O explicit
   exclusions. Validation checks D = O union (union_T S_T) and uniqueness of
   ownership. Thus no element of D is silently omitted. This does not prove that
   D equals every feasible real-world attack. A hidden channel or false scope
   premise defeats that stronger claim, so the record fixes
   `world_scope_truth_verified=false`.
4. **Exact replay.** Integer rational arithmetic preserves exact comparison of
   represented finite probabilities; outward display conversion cannot change
   the comparison. This closes rounding counterexamples in the revised optimizer
   path, not every numeric operation in Python or every supplied theorem premise.
5. **Integrity versus truth.** A secure signature binds an authenticated key to
   bytes; semantic replay binds those bytes to the supplied request/policy/scope.
   Neither proves honest data collection, key custody, complete live channels,
   current registry state or atomic activation. Offline records therefore cannot
   issue deployment authority.

## Migration and cleanup

| Contract | Previous | Current | Required action |
|---|---|---|---|
| Assessment report / signed manifest | 5 / 3 | 6 / 4 | Reassess original request under the current engine and re-sign after validation |
| Optimization request/report/manifest | 4 | 5 | Supply original assessment request path and SHA-256; bind policy games; re-optimize and re-sign |
| Release protocol run / verification | 1.1 / 2 | 1.2 / 3 | Rebuild/re-sign with authenticated_v2; use authorization_recorded/deployment_recorded, not issuance claims |
| Assurance scope/record/signature/acceptance/gate | Absent | 1 | New explicit contracts; no automatic acceptance or inferred scope approval |

Assessment request 5 and policy 3 retain their JSON shapes. New semantic checks
can reject old values despite unchanged shapes; do not just change version tags,
hashes or signed payloads to bypass validation. Reuse of valid underlying evidence
requires the approved collection context, policy and provenance still to match.

The deterministic manifest indexes **37 current schemas**. The 32 superseded
schema files were removed from `schemas/`, not silently overwritten. This local
checkout retains a SHA-256-checked recovery copy and manifest at
`output/retired-schemas-20260907/`. That ignored folder is not a distributed
archive: historical bytes also remain in Git at
`0145b3c92b2daa3a84bb288b89117c3ca0317073:schemas/<filename>`.
Retain the matching old runtime, dependency lock and trust material for historical
replay. Old schemas alone are insufficient.

No retained experiment result, preregistration or counterproof package was
restamped. The subsequent documentation cleanup retired duplicate narrative and
paper drafts into `output/md-cleanup-20260907/retired-markdown.zip`; measured
results, manifests and the generated ceiling report remain intact. A source-hash
failure after this code change is expected protection, not a reason to rewrite
the old registration.
Windows portability fixes do not establish a new scalability result. Directory
durability and peak-memory measurements must retain their platform qualification.

## Verification and unresolved obligations

The new regression suites cover contract laundering, exact-bound and game
mismatches, lifecycle context/signature/time tampering, corrupted-prefix append,
all four dispositions, unsupported attacker/channel enlargement and fail-closed
signed replay. Some disposition unit tests isolate classification with mocks;
the separate synthetic crossing integration tests actual sampled evidence through
the engine and gate. Neither is a trained-model privacy benchmark.

```bash
PYTHONPATH=src python scripts/generate_schema_manifest.py --write --refresh-schemas
PYTHONPATH=src python scripts/generate_schema_manifest.py --check
PYTHONPATH=src:tests:. python -m unittest discover -s tests
python scripts/check_markdown_links.py
```

Use semicolons instead of colons in `PYTHONPATH` on Windows. Run the existing
formal verifier with its pinned Lean toolchain for the unchanged abstract proofs.
The current-validation receipts are separate from older benchmark seals.

Still open: institutional trust and scope approval; attested worker truth and
resource enforcement; complete live-interface correspondence; authenticated
complete portfolio state and atomic budget commit; enforced gateway leases,
monitoring and revocation; immutable anchored retention; statistically valid
cross-threat/lifetime composition; formal refinement of the running Python and
crypto implementation; and new prospectively registered scalability experiments.
Those cannot honestly be closed by deleting files or marking tests green.
