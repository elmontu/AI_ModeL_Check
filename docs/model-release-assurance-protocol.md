# Model Release Assurance Protocol (MRAP/1.0)

**Status:** candidate normative specification with a machine-checked authorization-integrity and finite statistical-accounting core

**Framework version:** 0.7.0
**Implementation status:** the repository implements conformance levels 0--2 only; it cannot issue an MRAP production authorization

## 1. Purpose and normative boundary

MRAP specifies the end-to-end process by which a proposed model release may become an active, time-limited release. It defines the participants, immutable objects, signed messages, state machine, admissibility gates, atomic registry operation, gateway behavior, monitoring, and scoped assurance claims. Only the authorization-integrity and finite statistical-accounting core identified in Section 13 is machine checked; the entire engineering protocol is not formally verified.

MRAP is an institutional model-governance protocol, not a game-theoretic decision rule. Its governance core defines legitimate purpose and scope, decision rights, accountable ownership, independent challenge, affected-party consideration, conflict controls, non-compensable evidence requirements, reasoned and contestable decisions, deployment binding, incident response, reassessment, and retirement. The [governance-core specification](governance-core.md) states this architecture and its implementation boundary.

The words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, and **MAY** have the meanings in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when written in capitals.

An assessment report, optimization report, mathematical certificate, signature, or audit-log entry is **not** an authorization. A release is authorized only when its authorization record and the corresponding portfolio transition have been committed by the authoritative registry. A release is active only when the gateway has independently verified that committed record and emitted an activation receipt.

The finite `protocol-solve` command in this repository solves an evidence-gate soundness--liveness frontier. It is a meta-analysis used while designing an evidence plan; it does not execute MRAP and its certificate cannot authorize a release.

## 2. Security and assurance objective

Fix a real deployment world \(\omega\), authoritative pre-release state \(\Sigma_n\), registered release instance \(I\), and candidate configuration \(c\). The policy-defined acceptability predicate is

\[
\mathsf{Accept}(\Sigma_n,I,c,\omega)\in\{0,1\}.
\]

It is true only when every mandatory privacy, security, utility, fairness, legal, operational, population, transfer, and cumulative-portfolio obligation is satisfied for the exact bytes and complete interface that a recipient can observe. The desired substantive safety property is

\[
\mathsf{Active}(I,c)\Longrightarrow
\mathsf{Accept}(\Sigma_n,I,c,\omega),
\]

subject to the explicitly budgeted statistical failure probability, cryptographic assumptions, infrastructure assumptions, and adequacy of the policy/world model. This substantive property is an assurance objective, not an unconditional machine-checked theorem.

The machine-checked security property is narrower: within the formal transition semantics, any reachable `ACTIVE` state must have passed the registered evidence and selection predicates, completed a successful compare-and-swap authorization commit, retained exact artifact/interface identity, and remained inside its modelled authorization lifetime. Section 13 states the exact theorem and the boundary between this invariant and the substantive objective.

MRAP also aims for conditional liveness: a complete, valid instance containing a certified feasible candidate should reach `ACTIVE` when required services are available and the registry head remains stable. Safety takes priority over liveness. Missing, stale, contradictory, unverifiable, or out-of-scope input produces refusal, reassessment, or redesign.

## 3. Participants and separation of duties

| Symbol | Role | Protocol responsibility |
|---|---|---|
| `PA` | Policy authority | Publishes policy, mandatory threat catalogue, trust roots, tolerances, error budgets, expiry rules, and accepted analyzer/certificate types |
| `SO` | Model owner/submitter | Registers the proposed artifact, complete release interface, intended recipients, utility purpose, and candidates |
| `PS` | Population steward | Approves the population frame, protected unit, prior, neighboring relation, and scope snapshots |
| `CG` | Configuration generator | Produces the frozen candidate set and, when rejection is possible, a replayable completeness certificate |
| `EW` | Evidence authority/worker | Collects evidence under a frozen plan in an isolated, attested environment and signs source-observed bindings |
| `AS` | Assessor | Replays evidence, checks assumptions and scope, and signs typed assessment reports |
| `OP` | Optimizer | Applies the frozen policy to every submitted candidate and signs the deterministic selection report |
| `AR` | Authorizing authority | Reviews governance obligations and submits an authorization commit request; it cannot alter assessment values |
| `PR` | Portfolio registry | Maintains the authoritative linearizable state, performs compare-and-swap commits, and issues inclusion-verifiable authorization receipts |
| `GW` | Release gateway | Serves only bytes and interfaces named by a live registry authorization and emits activation/suspension receipts |
| `MO` | Monitor/auditor | Checks drift, incidents, expiry, ledger consistency, registry history, and gateway conformance; requests suspension or revocation |
| `IA` | Incident authority | Coordinates containment, exposure assessment, evidence preservation, revocation, and recovery |

A production deployment MUST identify each actor, its approved keys, and its allowed message types. `AS`, `AR`, and `GW` SHOULD be separately controlled. A policy MAY require additional independent assessors or four-eyes approval. One principal MAY hold multiple roles only when the policy's trust profile expressly permits it; the resulting trust concentration MUST be recorded.

The current offline repository can act as part of `AS` and `OP`. It does not implement authoritative `PR`, `GW`, identity, worker attestation, or continuous `MO` services.

## 4. Trust and adversary model

The recipient and submitter may be curious, colluding, or malicious. Artifacts and evidence inputs may be hostile. Network messages may be replayed, reordered, delayed, or modified. Concurrent submissions may target the same portfolio state. A compromised worker may fabricate results unless the selected trust profile requires independent replay or attestation.

MRAP relies on these explicit assumptions:

1. approved signature schemes are existentially unforgeable for the adversary and keys are correctly bound to roles;
2. the hash and canonicalization suite is collision resistant for protocol objects;
3. the registry implements a linearizable compare-and-swap operation and protects its signing key;
4. the gateway faithfully verifies the registry, artifact, interface, controls, expiry, and revocation status;
5. each statistical procedure satisfies its declared simultaneous-coverage guarantee under its frozen collection model;
6. formal certificates and exact/outward-rounded replay procedures are sound for their encoded premises; and
7. the policy, threat set, population definition, release interface, world model, and evidence assumptions are complete and correct enough for the claimed scope.

Cryptographic binding proves which bytes an actor signed. It does not prove that the evidence is true, that the world model is complete, or that the policy is ethically or legally adequate. Section 17 records further non-claims.

### 4.1 Supplemental strategic stress tests

MRAP's role permissions and transition invariants are enforcement semantics, not
a proof that rational participants prefer to comply. A deployment MAY add a
supplemental strategic stress-test certificate using
[Section 5 of the mathematical appendix](mathematical-foundations.md), but it
MUST NOT use predicted compliance or attacker deterrence to remove a mandatory
technical or governance gate. Incentive analysis is defense in depth; it does
not determine legitimate purpose, legal authority, affected-party
acceptability, distributive fairness, accountability, or authorization.

Every strategic problem MUST identify the accountable model owner, decision
authority, independent review body, affected-party groups, governance
objective, conflict-of-interest controls, contestation process, and
incident/retirement authority. Every resulting certificate MUST state that its
governance-decision effect and authorization effect are `none`.

Any statement using “best response,” “incentive compatible,” “deterrent,” or
“equilibrium” MUST bind:

- players and private types, timing, observable information, actions, and
  possible collusion;
- payoff components with units, affected-party perspective, source, date, and
  uncertainty intervals;
- audit/detection/validation probabilities with prospective positive controls
  and simultaneous uncertainty bounds;
- technically and legally enforceable consequences after limited liability,
  jurisdiction, collection, and delay;
- the exact solution concept, pessimistic follower tie rule, strict incentive
  margin, and replayable computation or closed-form certificate;
- causal or empirical justification for behaviorally interpreted costs and
  response functions; and
- sensitivity results over every registered uncertain primitive.

The certificate is inconclusive if an omitted material type is found, the
equilibrium action changes within the uncertainty set, the consequence is not
credible, or commitment/observability assumptions fail. Quantal-response or
other bounded-rationality models MAY be reported as sensitivity analyses but
MUST NOT replace the registered worst-case best response without deployment-
specific validation.

The evidentiary basis and hallucination controls for these requirements are
recorded in the
[primary-source game-theory review](game-theory-literature-review.md). The
repository implements a design-time exact-rational interval evaluator, not a
behaviorally calibrated solver or production parameter registry.

## 5. Cryptographic object model

Every protocol object has a versioned type, instance identifier, issuer, issue time, optional expiry, payload, predecessor references, and signature block. Production implementations MUST use a single approved canonical encoding. JSON deployments SHOULD use [RFC 8785 JSON Canonicalization](https://www.rfc-editor.org/rfc/rfc8785); clearance-critical numbers MUST be encoded as integers, exact rationals, or policy-approved decimal strings rather than implementation-dependent binary floating point.

For type `T` and payload `x`, define a domain-separated digest

\[
\mathsf{Digest}_T(x)=
H(\texttt{"MRAP/1.0"}\parallel 0x00\parallel T\parallel 0x00\parallel
\mathsf{Canonical}(x)).
\]

The signed envelope is

\[
M=(\texttt{MRAP/1.0},T,\mathit{instance},\mathit{message\_id},
\mathit{issuer},\mathit{role},\mathit{issued\_at},\mathit{expires\_at},
\mathit{predecessors},\mathit{payload}),
\]

with signature \(\sigma=\mathsf{Sign}_{sk}(\mathsf{Digest}_T(M))\). A verifier MUST reject an unknown type or version, noncanonical payload, invalid role/key binding, duplicate message identifier with different content, missing predecessor, invalid signature, expired message, or future timestamp outside the policy's clock-skew allowance.

Hashes bind at least:

- artifact bytes and every separately served component;
- the complete recipient-observable interface, including preprocessing, precision, explanations, metadata, retrieval, tools, memory, updates, randomness, query limits, concurrency, and related releases where applicable;
- policy and threat-catalogue snapshots;
- population frame, protected unit, prior, neighboring relation, and decision game;
- candidate set, controls, utility specification, evidence plan, raw evidence sources, reports, and certificates; and
- the expected portfolio-registry head and authorization expiry.

Mutable aliases such as model names, endpoint labels, or `latest` MUST NOT replace content digests.

## 6. Authoritative state and release instance

### 6.1 Long-lived state

At registry sequence \(n\), the authoritative state is

\[
\Sigma_n=(n,h_n,P_n,N_n,R_n,B_n,K_n,V_n),
\]

where:

- \(h_n\) is the state head;
- \(P_n\) is the active policy/threat-catalogue set;
- \(N_n\) contains dated population and protected-unit snapshots;
- \(R_n\) is the set of committed releases and their status;
- \(B_n\) is the statistical, privacy, query, and other cumulative budget ledger;
- \(K_n\) is the role/key/attestation trust registry; and
- \(V_n\) contains revocations, suspensions, incidents, and mandatory reassessment events.

The state head is

\[
h_n=H(\texttt{"MRAP-STATE-1"}\parallel n\parallel h_{n-1}\parallel
\mathsf{Canonical}(\Delta_n)),
\]

where \(\Delta_n\) is the complete committed transition. An authorized auditor MUST be able to obtain the transition, its signature, and an inclusion/consistency proof or equivalent independently replayable history. An append-only Merkle log is a suitable transparency mechanism; [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html) supplies a studied construction, but logging alone does not determine whether a release is safe.

### 6.2 Immutable release instance

A release instance is

\[
I=(\mathit{release\_id},h_0,p,n,a,i,t,C,u,E,\rho,e),
\]

where \(h_0\) is the expected registry head, \(p\) the policy snapshot, \(n\) the population snapshots, \(a\) the artifact commitment, \(i\) the complete-interface commitment, \(t\) the mandatory threat/decision-game set, \(C\) the candidate configurations, \(u\) the utility requirements, \(E\) the evidence plan, \(\rho\) the trust profile, and \(e\) the maximum authorization expiry.

Its identifier is

\[
\mathit{instance\_id}=\mathsf{Digest}_{\texttt{ReleaseInstance}}(I).
\]

Changing any field creates a new instance. A stale-head retry MUST rebase and re-evaluate portfolio obligations; it cannot relabel the old result with a new head.

## 7. Protocol messages

| Type | Issuer | Required semantic content |
|---|---|---|
| `PolicySnapshot` | `PA` | Policy/threat versions, tolerances, accepted evidence classes, error-budget ledger, decision rights, conflict controls, contestation and consultation requirements, trust profile, role keys, expiry/reassessment rules |
| `Registration` | `SO` | Legitimate purpose and prohibited uses, accountable owner, affected-party groups, artifact/interface commitments, recipients, populations, protected units, candidate-set commitment, expected registry head |
| `EvidencePlan` | `AS` + required approvers | Mandatory Bayesian decision problems and, when used, supplemental strategic stress-test records; sources, affected-party/impact evidence and consultation plan, sampling design, multiplicity family, allocated errors, worker/image identities, positive controls, stopping and exclusion rules |
| `EvidenceBundle` | `EW` | Raw-source digests, source-observed context, worker attestation, measurements, failures, and plan digest |
| `AssessmentReport` | `AS` | Per-candidate, per-threat interval and direction, scope, affected-party impacts, adverse findings, dissent, assumptions, replay result, transfer/portfolio result, optional strategic stress-test status with no decision effect, and `clear/block/inconclusive` status |
| `OptimizationReport` | `OP` | All candidates, feasibility predicates, selected candidate or exhaustive refusal, deterministic tie-break, report/certificate digests, expected head and expiry |
| `AuthorizationCommitRequest` | `AR` | Selected candidate, all predecessor digests, reasoned governance decision, authority and separation checks, conflict disclosures, affected-party evidence, objections and their disposition, non-overridden mandatory gates, operating/retirement conditions, expected head, budget delta, expiry, nonce, and requested gateway constraints |
| `AuthorizationReceipt` | `PR` | Durable registry entry, old/new heads, selected artifact/interface/control digests, committed budget delta, expiry, sequence, and registry proof |
| `ActivationReceipt` | `GW` | Authorization digest, registry verification time/head, remeasured served bytes/interface/controls, endpoint identifier, lease expiry |
| `LifecycleEvent` | `MO`, `GW`, `PR`, or authorized actor | Monitor result, complaint/contestation, drift, incident, suspension, revocation, expiry, reassessment, replacement, or decommission event |

Each message MUST reference all immediate predecessors needed to replay its decision. Reports MUST retain negative and inconclusive evidence; a producer cannot omit an inconvenient mandatory result and still satisfy message completeness.

## 8. Normative state machine

Each instance has exactly one current protocol state. The registry, not a client-side report, is authoritative for `AUTHORIZED`, `ACTIVE`, `SUSPENDED`, `EXPIRED`, and `REVOKED`.

| From | Event and mandatory actor | To | Mandatory conditions |
|---|---|---|---|
| `DRAFT` | valid `Registration` by `SO` | `REGISTERED` | Identity, legitimate purpose, prohibited uses, accountable owner, affected parties, schema, immutable artifact/interface/candidate hashes, policy and current head captured |
| `REGISTERED` | approved `EvidencePlan` | `PLAN_FROZEN` | Threat, population and governance-evidence completeness; consultation/impact plan registered; error allocated before observation; workers and stopping rules fixed |
| `PLAN_FROZEN` | complete `EvidenceBundle` set | `EVIDENCE_FROZEN` | Source, context, worker, positive-control, raw-data and plan bindings verified; collection closed |
| `EVIDENCE_FROZEN` | signed `AssessmentReport` | `ASSESSED` | Every mandatory candidate/threat cell is `clear`, `block`, or `inconclusive`; arithmetic/certificates replay |
| `ASSESSED` | signed `OptimizationReport` | `OPTIMIZED` | Deterministic feasible-set evaluation; utility before minimization; exhaustive proof if outcome is `reject` |
| `OPTIMIZED` | valid commit request by `AR` | `COMMIT_PENDING` | Reasoned governance decision, authority, independent challenge, conflicts, affected-party evidence, objections/disposition, conditions and retirement owner complete; no mandatory gate overridden; selected candidate unchanged; evidence and policy live |
| `COMMIT_PENDING` | successful registry CAS | `AUTHORIZED` | Expected head matches; complete joint portfolio and budgets valid; authorization and state delta committed atomically |
| `AUTHORIZED` | valid gateway activation | `ACTIVE` | Registry membership/current status checked; served bytes/interface/controls exactly match; activation lease issued |
| `ACTIVE` | material change, monitor breach, lease loss | `SUSPENDED` | Gateway stops new access before or atomically with event recording |
| `ACTIVE` or `SUSPENDED` | expiry | `EXPIRED` | Gateway stops new access; retained outputs follow records policy |
| any non-revoked state | authorized revocation | `REVOKED` | Registry commits revocation and gateway denies new access |
| any pre-authorization state | incomplete/remediable result | `REDESIGN_REQUIRED` | No authorization; a changed proposal starts a new immutable instance |
| `ASSESSED` or `OPTIMIZED` | proved infeasibility under complete candidate set | `REJECTED` | Exhaustive-search premise is certified; otherwise use `REDESIGN_REQUIRED` |
| any state before `AUTHORIZED` | stale head, replay, conflict, timeout | `ABORTED` | No release; rebase against the new state and repeat affected stages |

No transition may skip a state. Repeated messages are idempotent only when their canonical digest is identical. A different message reusing an identifier is a protocol violation. `REVOKED`, `EXPIRED`, `REJECTED`, and `ABORTED` are terminal for the instance.

The principal path is therefore:

```text
DRAFT -> REGISTERED -> PLAN_FROZEN -> EVIDENCE_FROZEN
      -> ASSESSED -> OPTIMIZED -> COMMIT_PENDING
      -> AUTHORIZED -> ACTIVE -> SUSPENDED / EXPIRED / REVOKED

pre-authorization failures -> REDESIGN_REQUIRED / REJECTED / ABORTED
```

## 9. Admissibility gates

The following gates are conjunctive. `PASS` at one gate cannot compensate for failure at another.

| Gate | Requirement | Failure result |
|---|---|---|
| `G0 Identity` | Actor authenticated; key live and authorized for message role | `ABORTED` |
| `G1 Encoding/integrity` | Version, schema, canonicalization, hashes, signatures, times, predecessors valid | `ABORTED` |
| `G2 Policy` | Applicable policy/threat catalogue frozen independently of results; no unauthorized override | `REDESIGN_REQUIRED` or `ABORTED` |
| `G3 Scope` | Legitimate purpose, prohibited uses, accountable owner, affected parties, artifact, complete interface, recipients, population, protected unit, prior and Bayesian decision problems complete; every supplemental strategic stress test has governance context and complete players/timing/information/actions/payoffs | `REDESIGN_REQUIRED` |
| `G4 Candidate/search` | Candidate set frozen; `reject` backed by an approved completeness certificate | downgrade `reject` to `REDESIGN_REQUIRED` |
| `G5 Evidence plan` | Evidence class can answer the stated claim; sampling, multiplicity, stopping, controls and budget preregistered | `REDESIGN_REQUIRED` |
| `G6 Evidence execution` | Source-observed bindings, attested worker, raw data, positive controls, exclusions and replay valid | `INCONCLUSIVE`/`REDESIGN_REQUIRED` |
| `G7 Statistical/formal` | Simultaneous coverage allocated; clearance uses only exact values or valid ceilings; critical arithmetic exact/outward rounded | `INCONCLUSIVE` |
| `G8 Transfer` | Direct evidence or verified safe-direction information reduction from assessed to released experiment | `INCONCLUSIVE` |
| `G9 Portfolio` | Complete joint observable portfolio directly assessed, validly composed, or robustly upper bounded at current head | `INCONCLUSIVE` or `ABORTED` |
| `G10 Utility/choice` | All mandatory privacy and utility constraints pass before deterministic least-information tie-break | `REDESIGN_REQUIRED`/`REJECTED` |
| `G11 Governance` | Decision authority and accountable owner identified; required independent challenge completed; conflicts disclosed and controlled; affected-party/impact evidence and recorded objections considered; reasons, conditions, contestation route, incident owner, expiry and retirement rule present; no mandatory gate compensated or overridden; any strategic stress-test claim has strict robust margins, credible consequences, and no decision effect | `REDESIGN_REQUIRED` |
| `G12 Atomic commit` | CAS against expected head; budget and authorization are one durable transition | `ABORTED` |
| `G13 Activation` | Gateway checks registry membership/status and rehashes exact served bytes/interface/controls | no activation or `SUSPENDED` |
| `G14 Monitoring` | Lease, drift, incident, query/budget and revocation checks remain live | `SUSPENDED`, `EXPIRED`, or `REVOKED` |

Attack success may provide a lower bound and block. Attack failure supplies no clearance ceiling. Unknown model families and unsupported interactive protocols cannot pass `G5`--`G9` merely because they are present in a coverage catalogue.

## 10. Reference algorithms

### 10.1 Freeze an instance

```text
Freeze(registration, policy, current_head):
  verify G0--G3
  require registration.expected_head == current_head
  freeze purpose, prohibited uses, accountable owner, decision authority,
      affected-party groups, conflict controls and contestation requirements
  derive mandatory threats from policy, model family, interface and portfolio
  obtain frozen candidate set and utility requirements
  if strategic claims are made, freeze players, timing, information,
      payoff provenance/uncertainty, solution concept and strict margins
  allocate statistical error before evidence is observed
  approve workers, source data, positive controls, stopping/exclusion rules
  sign EvidencePlan(instance_digest, allocations, complete plan)
  return PLAN_FROZEN
```

If the candidate set or policy is selected after inspecting audit outcomes, the plan MUST explicitly cover that selection. Otherwise the instance is invalid, not retroactively repaired.

### 10.2 Collect and assess

```text
Assess(instance, evidence_bundles):
  verify G0--G6 for every required bundle
  for each candidate c and mandatory threat t:
      replay exact/formal/statistical evidence
      classify every result as exact, ceiling, floor, or screen
      apply transfer and complete-portfolio checks
      calculate [L[c,t], U[c,t]] with declared simultaneous coverage
      status[c,t] = BLOCK if L[c,t] > tolerance[t]
                    CLEAR if U[c,t] <= tolerance[t]
                    INCONCLUSIVE otherwise
  retain every result, warning, assumption and failure
  sign AssessmentReport
  return ASSESSED
```

### 10.3 Optimize

```text
Optimize(instance, assessment_reports):
  verify G0--G10 and exact report-to-candidate bindings
  feasible = candidates passing every mandatory privacy, utility and control gate
  if feasible is nonempty:
      select deterministic policy tie-break among Blackwell-minimal feasible options
      outcome = release_as_proposed or release_with_controls
  else if candidate enumeration is certified complete:
      outcome = reject
  else:
      outcome = redesign_required
  sign OptimizationReport(expected_head, selected candidate or refusal)
  return OPTIMIZED or terminal refusal
```

### 10.4 Atomic authorization

Let `entry` contain all immutable authorization fields and `budget_delta`. The registry exposes one linearizable operation:

```text
Commit(request):
  verify G0--G12 and replay all mandatory predecessor digests
  require a reasoned governance decision within the named authority
  require independent challenge, conflict disclosures, affected-party evidence,
      objection dispositions, operating conditions and retirement rule
  require every mandatory gate passed without compensation or override
  transaction:
      require registry.head == request.expected_head
      require request.nonce unused
      require selected configuration and evidence remain live
      re-evaluate complete portfolio and all cumulative ledgers
      require budget_delta is available
      new_head = H("MRAP-STATE-1", sequence+1, old_head, canonical(entry))
      authorization = Sign_PR(entry, old_head, new_head, sequence+1)
      atomically persist entry, budget_delta, authorization and new_head
  publish AuthorizationReceipt plus inclusion/consistency proof
  return AUTHORIZED
```

The registry MUST reveal a signed authorization only if its corresponding entry committed. The gateway MUST additionally verify inclusion/current status, so a detached signature is insufficient. A stale head, duplicate nonce, expired predecessor, or concurrent budget change aborts the transaction.

This compare-and-swap requirement follows the standard idea of [linearizability](https://doi.org/10.1145/78969.78972): each successful state transition appears to take effect at one point between invocation and response.

### 10.5 Activate and monitor

```text
Activate(receipt, endpoint):
  verify PR signature, inclusion, current status, expiry and allowed gateway identity
  hash artifact bytes and canonical complete interface actually served
  attest technical controls and query/budget enforcement
  require exact equality with authorization
  issue short-lived ActivationReceipt and begin monitoring
  return ACTIVE

Monitor(active_release, observation):
  check authorization lease, expiry, revocation, hashes, controls, population drift,
        incidents, policy changes, query limits and cumulative budgets
  if any mandatory condition is unknown or violated:
      stop new access and commit LifecycleEvent
      return SUSPENDED / EXPIRED / REVOKED
```

Evidence workers and assessors mirror the attester--verifier--relying-party separation in the IETF [RATS architecture](https://www.rfc-editor.org/rfc/rfc9334.html): signed evidence is appraised under policy, and the downstream relying party consumes an appraisal result. MRAP adds model-release-specific statistical and portfolio obligations; RATS conformance alone is not sufficient.

## 11. Error-budget protocol

Let \(J_N\) be every statistical coverage family whose output can influence the first \(N\) committed releases, including adaptive candidate, threshold, subgroup, threat, portfolio, and repeated-release selection. Before observing its data, family \(j\) receives allocation \(\alpha_j\). The ledger requires

\[
\sum_{j\in J_N}\alpha_j\le \alpha_{\mathrm{ledger},N}.
\]

Within a family, the procedure MUST provide simultaneous coverage over every value that the downstream decision may select. Reusing the same evidence does not spend error again when the original simultaneous event already covers the reuse; collecting new evidence or making a new uncovered selection does. Dependence does not invalidate the union bound, although it may make it conservative.

Sequential deployments MUST define a lifetime ledger or an approved alpha-spending/e-process rule. A per-report 95% interval repeated indefinitely is not a 95% lifetime release guarantee. Privacy-loss, query, and operational budgets are separate ledgers and MUST NOT be mixed numerically with statistical coverage error.

## 12. Protocol invariants

Every conforming implementation preserves these invariants:

1. **Binding:** every decision and active endpoint identifies the same immutable instance, artifact, interface, population, policy, game, portfolio predecessor, and selected configuration.
2. **No report-as-authorization:** `ASSESSED` and `OPTIMIZED` cannot cause gateway service.
3. **Complete mandatory conjunction:** authorization requires every mandatory gate; an average score cannot mask one failed threat.
4. **Evidence direction:** floors may block; only exact values or valid ceilings may clear.
5. **Portfolio induction:** each state transition checks the complete new joint portfolio against the current committed predecessor.
6. **Freshness:** expiry, revocation, policy change, drift, or changed bytes/interface prevents continued service without the prescribed reassessment.
7. **Single-head commit:** no authorization can commit against a state other than its signed expected predecessor.
8. **Gateway fidelity:** the served release is byte- and interface-equivalent to the live authorization.
9. **Trace completeness:** failures, refusals, supersessions, and revocations remain auditable; successful messages cannot erase them.
10. **Fail-closed uncertainty:** missing validation or unreachable authoritative state stops progression or suspends service.

## 13. Formal protocol guarantees

The authoritative proof scope is [`formal/lean`](../formal/lean/) and the exact interpretation is documented in [Formally verified protocol core](formal-verification.md). Lean checks unbounded inductive reachability over the abstract transition relation, not a finite collection of example traces.

The proof target is deliberately authorization integrity rather than an unconditional `ACTIVE`-implies-acceptable theorem. The latter would be circular if its proof assumed that the policy, evidence, threat catalogue, registry, gateway and every deterministic gate were already complete and sound. The formal model therefore discharges trace-level obligations it can state without those assumptions, while the conditional engineering corollary below retains the external scientific and implementation obligations explicitly. Exact finite rational weights were chosen for the statistical core so error-ledger arithmetic is reproducible and free of floating-point or independence assumptions. The full rationale is recorded in the formal-verification document.

### Machine-checked Theorem FV-AUTH-1: authorization integrity

Let `Reachable initial current` be the inductively generated set of states starting from an `Initial` state and using only the role-indexed `Step` relation. The Lean theorem `reachable_authorization_integrity` proves that every such state satisfies `AuthorizationIntegrity`.

Consequently, `active_implies_committed_clear_and_bound` proves that a reachable `ACTIVE` state has all registered evidence, coverage, control, assessment and selection predicates; an authorization request; a successful atomic commit; an issued authorization; a committed head different from the registered predecessor; deployed artifact and interface values identical to the registered values; and a modelled clock strictly before expiry.

This is an abstract authorization-integrity theorem. Step constructors assume the effects attributed to authenticated roles, the registry and gateway. It does not prove those implementations or the scientific truth of a gate.

`valid_active_trace_exists` constructs a complete valid trace to `ACTIVE` in the kernel. This is a non-vacuity result: it shows that the safety invariant is not true merely because activation is unreachable. It is not a real-service liveness guarantee.

### Machine-checked Theorems FV-MSG/FV-COMP: authenticated execution

`EnvelopeAdmissible` requires a symbolic authenticated message to carry an authorized role/action pair, exact release/artifact/interface/registry-head bindings, an unused nonce, a non-future issue time and a live expiry. Lean proves that accepted messages have all of these properties and that replay, artifact mismatch, known signer compromise and expiry are rejected.

The message model is connected to the lifecycle model by `AuthenticatedStep`: its admissible envelope supplies the role and action indices of the exact `Step` performed, and the consumed nonce is recorded. `authenticated_reachable_projects` proves that every trace in this composed semantics projects to a lifecycle trace. `authenticated_reachable_authorization_integrity` and `authenticated_active_implies_committed_clear_and_bound` therefore carry the lifecycle safety theorem into the authenticated semantics.

The envelope's `authenticated` flag abstracts a successful approved cryptographic verification. These theorems do not verify Ed25519, Python canonicalization, certificate issuance, key storage or compromise discovery. Unknown key compromise remains outside the claim.

### Machine-checked Theorem FV-RBAC-1: transition authorization

`every_step_is_role_authorized` proves that every constructible transition is permitted for its role/action index. This excludes role-confused transitions inside the model. It does not prove real credential issuance, key custody, identity federation or resistance to principal compromise.

### Machine-checked Theorem FV-CAS-1: stale-head exclusion

`stale_head_second_commit_fails` proves for the specified compare-and-swap function that, after one successful commit strictly advances an append-only registry head, another request using the old expected head returns failure. Strict advancement rules out ABA reuse of an earlier head. Applying this result to a service requires a refinement argument from that service to the specified linearizable operation; MRAP does not currently provide that refinement proof.

### Machine-checked Theorems FV-DEP: ideal deployment

`MRAP.Deployment` specifies the mathematically relevant deployment as an ideal
functionality. Its atomic `commit` checks the expected head and sequence,
strict head advancement, nonce freshness, cleared gates, and a live deadline,
then binds one authorization record and receipt to the release, artifact,
interface, predecessor, sequence, expiry, and nonce. `activate` checks that the
record is current and authorized, rechecks measured artifact/interface
identifiers, and creates a gateway lease bounded by the authorization expiry.
`CanServe` is a per-request predicate that requires a current active record,
exact bindings, matching observed head and sequence, and live lease and
authorization deadlines.

The kernel checks the following consequences:

1. commit succeeds exactly when its admissibility predicate holds, and every
   success is atomic, bound, sequence-advancing, and nonce-consuming;
2. replaying a committed request, reusing a consumed nonce, and a concurrent
   request using the stale predecessor are rejected;
3. activation succeeds exactly when the current authorization, measurements,
   and time bounds are admissible; every success can serve, while every serving
   state has a current active gate-cleared authorization with exact bindings;
4. artifact or interface substitution, a stale gateway observation, lease
   expiry, and authorization expiry cannot serve;
5. suspension or revocation invalidates an existing gateway; and
6. every reachable unexpired lifecycle `ACTIVE` state has a serving ideal
   realization, with a separate concrete executable commit–activate–serve
   witness establishing non-vacuity.

These are universal theorems about the ideal semantics, not tests of selected
traces. Their assumptions are also the refinement contract: registry updates
are atomic and durable, observations and time are authentic, identifiers
faithfully represent the served bytes/interface, and gateways enforce
`CanServe` for every request. No theorem here proves PostgreSQL transactions,
distributed consensus, networking, clock fidelity, Ed25519, Python, or a real
gateway implementation.

### Machine-checked Theorem FV-STAT-1: finite false-authorization budget

For finite rational experiments represented using a positive common denominator, `finite_false_authorization_bound` proves

\[
\Pr(A)\leq\sum_{j\in J_N}\Pr(F_j),
\]

where `SoundOutcome.sound` supplies the premise that each false-authorization outcome \(A\) belongs to at least one registered component failure event \(F_j\). `finite_false_authorization_within_budget` then proves \(\Pr(A)\leq\alpha\) whenever the summed component mass is at most the allocated budget. `registered_component_budget_controls_false_authorization` strengthens the accounting interface: each registered component carries its own failure mass, allocation and within-allocation proof; the component ledger must reconcile exactly with the modeled failure table; the allocations must fit the total budget; and the total budget must fit the probability denominator. No independence assumption is used.

The inclusion \(A\subseteq\bigcup_jF_j\), the mapping from an empirical procedure to each \(F_j\), and its advertised coverage are external proof obligations. The theorem must not be read as manufacturing statistical validity from an arbitrary test.

### Conditional engineering corollary (not machine checked)

For a horizon of \(N\) committed releases, define

\[
\mathcal E_N=
\left(\bigcap_{j\in J_N}\mathcal C_j\right)
\cap\mathcal C_{\mathrm{adequacy}}
\cap\mathcal C_{\mathrm{binding}}
\cap\mathcal C_{\mathrm{registry}}
\cap\mathcal C_{\mathrm{gateway}}.
\]

If the acceptability predicate and threat model are complete for the claim; every deterministic and scientific gate is sound; statistical failure events cover every way an unacceptable release could nevertheless clear; cryptographic binding holds; and the registry and gateway refine their abstract specifications, then an active release is acceptable on \(\mathcal E_N\). If \(\Pr(\mathcal C_j^c)\leq\alpha_j\) and the combined computational failure advantage is at most \(\nu_N(\kappa)\), the ordinary union bound gives

\[
\Pr[\exists\text{ active unacceptable release among the first }N]
\leq \sum_{j\in J_N}\alpha_j+\nu_N(\kappa).
\]

This paragraph is a conditional assurance-case argument, not a Lean theorem. In particular, its adequacy and refinement premises are substantial and cannot be discharged by hashes, signatures or successful compilation.

### Remaining proof obligations

Portfolio preservation and distributed conditional liveness remain mathematical proof sketches, not machine-checked claims. The formal non-vacuity witnesses show that valid abstract lifecycle and ideal commit–activate–serve executions exist; they do not establish real-service progress. A production claim still requires verified or independently validated refinement of message parsing, signature and canonicalization checks, concrete registry/gateway behavior, time/expiry behavior, and the Python transcript verifier to the formal semantics.

A faithful gateway can prevent new authorized observations after suspension, expiry or revocation takes effect, but cannot retract prior disclosures. The protocol is not claimed to realize an ideal functionality under universal composition.

## 14. Failure, recovery, and change rules

- **Hash/signature/schema failure:** abort; do not repair the received object in place.
- **Evidence or positive-control failure:** mark affected cells inconclusive and redesign/recollect under a new plan.
- **Policy/population/threat change before commit:** create a new instance or an explicitly versioned reassessment that reruns all affected gates.
- **Stale portfolio head:** abort, rebase, and rerun portfolio, budget, optimization, and approval checks at minimum.
- **Gateway mismatch:** do not activate; quarantine the package and open an incident.
- **Monitor uncertainty or loss of registry freshness:** suspend when the authorization lease expires; availability failure does not justify serving indefinitely.
- **Revocation:** append a registry event, notify all gateways, stop new access, preserve audit evidence, and assess prior exposure.
- **Rollback:** a previous model requires a new authorization against current state; an old expired receipt cannot be replayed.
- **Emergency path:** may accelerate actors and service-level targets but MUST NOT skip binding, mandatory evidence, atomic commit, gateway verification, or expiry.

## 15. Model-family adaptation

MRAP is model-family neutral at the control-flow level, not evidence neutral. `G3`--`G9` MUST instantiate the complete recipient interface and valid evidence for the actual system:

- classical and tree models include preprocessing, metadata, precision and prediction interfaces;
- generative models include decoding, prompts/system messages, retrieval, filters, tools and output transformations;
- agentic systems include tool authority, environment feedback, memory, concurrency and multi-step transcripts;
- online or continually learned systems include update rules and an authorization lease short enough to bound drift;
- composite/multimodal systems include every component and cross-component channel; and
- unknown families require an approved custom threat/evidence profile and cannot clear by catalog membership.

Watermark and canary tests remain scheme- and protocol-specific evidence. They do not substitute for complete privacy, safety, security, utility, and portfolio gates.

## 16. Conformance levels and current status

| Level | Required capability | Repository status |
|---|---|---|
| `MRAP-L0 Mathematical` | Replay finite decision, transfer, evidence-gate and portfolio certificates | Implemented for documented finite cases; authorization-integrity and finite union-bound cores are machine checked in Lean |
| `MRAP-L1 Assessment` | Validate immutable request/evidence context and emit typed per-threat reports | Implemented as an offline reference with stated arithmetic/analyzer limits |
| `MRAP-L2 Selection` | Deterministically evaluate submitted configurations and sign a bound optimization result | Implemented; signatures protect integrity, not evidence truth |
| `MRAP-L3 Authorization` | Authenticated roles, exact critical replay, authoritative linearizable registry, atomic portfolio/budget commit, durable authorization receipt | Authenticated offline transcript replay is implemented; authoritative identity/registry service and durable authorization issuance are not |
| `MRAP-L4 Enforcement` | Gateway byte/interface enforcement, leases, revocation, monitoring, incident and transparency operations | Not implemented |

Only a deployment conforming to all five levels may describe a release as authorized under MRAP/1.0. The current CLI outputs MUST be described as offline assessments, selections, certificates, or structural/authenticated transcript replays. They MUST NOT be relabelled `AuthorizationReceipt` or used directly by a serving gateway.

The repository includes a typed `ReleaseProtocolRun` contract version 1.1 and `release-protocol-verify` command. It replays the normative state machine, actor/role permissions, artifact-producer roles, exact-decimal assurance spending, event hash chain, assessment/selection preconditions, strict registry-sequence advancement, atomic compare-and-swap assertion, deployment digest equality, expiry, monitoring, suspension, revocation, and abort behavior. By default it also rehashes every referenced artifact file. The `structural_v1` profile does not authenticate actors. The `authenticated_v1` profile verifies domain-separated release-bound Ed25519 signatures for every event and artifact declaration against an external public-key trust store and rejects supplied compromised-key identifiers.

Both profiles remain conformance harnesses rather than an authoritative protocol service: they do not issue credentials, discover compromise, contact or implement a linearizable registry, enforce a gateway, verify remote attestations, or establish that the scientific contents of an artifact are true. A correspondence manifest prevents silent role/state/action drift, and adversarial mutation tests exercise concrete rejection behavior, but the Python verifier has not been proved to refine the Lean model.

Supply-chain attestations SHOULD link each independent actor's materials and products in the spirit of [in-toto](https://www.usenix.org/conference/usenixsecurity19/presentation/torres-arias), while the registry separately enforces model-release policy and state. NIST's [AI Risk Management Framework](https://doi.org/10.6028/NIST.AI.100-1) motivates lifecycle-wide governance and monitoring, but MRAP's typed messages, scoped formal invariants and conditional assurance argument are project-specific.

## 17. Explicit non-claims

MRAP/1.0 does not prove:

- equivalence between the Lean transition system and the Python verifier or any production implementation;
- completeness or correctness of a policy, world set, population, prior, threat catalogue, causal model, or acceptability predicate;
- truth of evidence merely because it is hashed, signed, attested, or logged;
- safety for an interface, recipient, population, time period, or related-release portfolio not bound into the instance;
- security of infrastructure, keys, worker implementations, the registry, or gateway without their stated operational controls;
- safe infinite-horizon operation from fixed per-release confidence intervals;
- that monitoring or revocation reverses information already disclosed;
- that one scalar score represents all privacy, security, utility, fairness, or legal obligations;
- incentive compatibility, attacker deterrence, equilibrium selection, or social welfare from role permissions, signatures, or unvalidated payoff tables;
- transferability of actor utilities, audit effectiveness, sanctions, effort costs, or behavioral-response parameters across sectors or time;
- universal composability, zero knowledge, differential privacy, or noninterference of the whole lifecycle unless separately specified and proved; or
- accreditation, legal compliance, or fitness for a particular deployment.

These are scope boundaries, not optional implementation tasks. A deployment may narrow the claimed scope, strengthen assumptions, or add evidence, but it MUST NOT silently erase an unproved premise.

## 18. Primary design foundations

- Herlihy and Wing. [Linearizability: A Correctness Condition for Concurrent Objects](https://doi.org/10.1145/78969.78972). *ACM TOPLAS*, 1990.
- Canetti. [Universally Composable Security: A New Paradigm for Cryptographic Protocols](https://doi.org/10.1109/SFCS.2001.959888). FOCS, 2001. Used to delimit, not claim, composable security.
- Torres-Arias et al. [in-toto: Providing Farm-to-Table Guarantees for Bits and Bytes](https://www.usenix.org/conference/usenixsecurity19/presentation/torres-arias). USENIX Security, 2019.
- IETF. [Remote ATtestation procedureS (RATS) Architecture](https://www.rfc-editor.org/rfc/rfc9334.html). RFC 9334, 2023.
- IETF. [Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162.html). RFC 9162, 2021.
- NIST. [Artificial Intelligence Risk Management Framework 1.0](https://doi.org/10.6028/NIST.AI.100-1). NIST AI 100-1, 2023.
- NIST. [Secure Software Development Framework 1.1](https://doi.org/10.6028/NIST.SP.800-218). NIST SP 800-218, 2022.
- NIST. [Guidelines for Evaluating Differential Privacy Guarantees](https://doi.org/10.6028/NIST.SP.800-226). NIST SP 800-226, 2025.
- NIST. [Artificial Intelligence Risk Management Framework: Generative AI Profile](https://doi.org/10.6028/NIST.AI.600-1). NIST AI 600-1, 2024.
- Blocki et al. [Audit Games](https://www.ijcai.org/Proceedings/13/Papers/017.pdf). IJCAI, 2013.
- Guo et al. [On the Inducibility of Stackelberg Equilibrium for Security Games](https://doi.org/10.1609/aaai.v33i01.33012020). AAAI, 2019.
- Miller, Milli, and Hardt. [Strategic Classification is Causal Modeling in Disguise](https://proceedings.mlr.press/v119/miller20b.html). ICML, 2020.

The statistical, differential-privacy, information-ordering, membership-inference, extraction, watermark, canary, XGBoost, and LLM foundations are developed in the [mathematical appendix](mathematical-foundations.md) and [literature review](literature-review.md).
