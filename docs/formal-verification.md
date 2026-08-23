# Formally verified protocol core

## Verification status

MRAP includes a machine-checked **authorization-integrity, ideal-deployment,
and finite statistical-accounting core**. The proof artifact is a Lean 4
transition system and ideal registry/gateway functionality, not a proof that
an arbitrary released model is safe. Lean checks all reachable traces of the
abstract system; this is not bounded-state testing.

The verified claim is deliberately narrower than the engineering protocol:

> Within the Lean transition semantics, an `ACTIVE` state is reachable only
> after the registered evidence, coverage, control, assessment and selection
> predicates hold; an authorization request and successful atomic commit have
> occurred; the committed head differs from the registered predecessor; the
> deployed artifact and interface equal the registered values; and the modelled
> clock is before expiry.

The ideal deployment layer makes this result operational inside the
mathematical model. It defines an atomic registry commit, activation against
measured artifact and interface identifiers, a bounded gateway lease, and a
per-request `CanServe` predicate. Lean proves that a successful ideal commit
and activation can serve the bound release; stale or replayed commits,
artifact/interface substitution, stale gateway state, lease or authorization
expiry, suspension, and revocation cannot serve. A concrete checked witness
shows that this path is executable rather than merely consistent on paper.

Separately, for a finite rational experiment represented by integer weights,
if every false authorization is covered by at least one registered component
failure event, the total false-authorization mass is no greater than the sum
of the component failure masses. No independence assumption is used.

The authenticated semantics are composed with the lifecycle semantics, rather
than proved in isolation. An `AuthenticatedStep` contains both an admissible
message envelope and the exact role/action-indexed `Step` it authorizes.
`authenticated_reachable_projects` proves that every authenticated execution
is a lifecycle execution, so the authorization-integrity theorem applies to
the composed system. A concrete valid trace reaching `ACTIVE` is also checked,
ruling out the vacuous explanation that the safety theorem holds only because
activation is impossible.

## Design rationale

The formalization is intentionally narrower than the original prose safety
claim. An implication such as `ACTIVE → Acceptable` is not informative if
`Acceptable` is obtained simply by assuming that every policy, evidence and
implementation gate is sound. Formalizing that argument would verify its
logical shape while leaving all of its difficult premises untouched. The Lean
core instead proves properties whose violations can be characterized inside a
protocol trace: authorization cannot be created without the registered gates
and atomic commit, release identity cannot change, terminal phases cannot be
reopened, role-confused actions cannot occur, and stale registry heads cannot
be reused.

The principal choices are:

1. **Inductive traces rather than sampled traces.** `Reachable` ranges over
   traces of arbitrary finite length. The proof is therefore not evidence that
   a chosen set of executions happened to pass; it is an invariant proof for
   every execution admitted by the transition relation.
2. **Role and action in the transition type.** A transition carries its actor
   and action as type indices. The authorization theorem can consequently say
   that every constructible step is permitted, rather than relying on a
   separate log field that might disagree with the transition performed.
3. **Immutable release identity.** Artifact, interface and registered
   predecessor are preserved by every step. This prevents a valid assessment
   of one object from becoming an authorization for another object within the
   model.
4. **Strictly increasing registry heads.** Equality-based compare-and-swap is
   insufficient if an old head can reappear through an ABA sequence. Requiring
   append-only head advancement and proving trace-wide monotonicity makes the
   stale-head theorem depend on an explicit condition that a real registry can
   be required to refine.
5. **Exact finite probability mass.** Natural-number weights and a positive
   common denominator represent finite rational experiments without
   floating-point rounding. This matches the protocol's auditable error ledger
   and gives a kernel-checked union bound without inventing an independence
   assumption.
6. **Adequacy as a visible premise.** The statistical theorem requires every
   false authorization to belong to at least one registered failure event.
   Making this inclusion explicit prevents the arithmetic proof from being
   misreported as evidence that the threat catalogue or empirical tests are
   complete.
7. **No unproved implementation correspondence.** The Lean model and Python
   verifier use related vocabulary, but syntactic similarity is not semantic
   refinement. Declaring this gap identifies the next meaningful verification
   problem instead of transferring a theorem to code by assertion.
8. **Small, reproducible proof base.** The package pins Lean, uses no external
   mathematical library, rejects proof placeholders and audits compiled axiom
   dependencies. This makes the review boundary inspectable and reproducible.
9. **Composed message and state semantics.** An accepted message is bound to
   release, artifact, interface, registry head, role, action, nonce and time.
   Its role and action are the indices of the lifecycle transition executed by
   the authenticated step. The projection theorem is the formal link between
   the two layers; it is not an implementation-refinement claim.
10. **Non-vacuity without overclaiming liveness.** A kernel-checked witness
    constructs a complete valid trace to `ACTIVE`. This shows the rules permit
    release, but it does not show that networks, people, registries or gateways
    eventually respond in a real deployment.
11. **Ideal deployment before infrastructure.** `Deployment.lean` specifies
    the smallest atomic registry and fail-closed gateway semantics needed by
    the protocol. This proves mathematical deployability and exposes the exact
    refinement target for later software. It does not verify PostgreSQL,
    distributed consensus, a network gateway, an operating-system clock, or
    durable storage.

This division produces two layers. The verified layer establishes protocol
authorization integrity and exact statistical accounting in the abstract
model. The assurance-case layer must separately justify scientific evidence,
policy completeness, cryptography, service implementations and refinement.
Keeping the layers separate is the main defence against a formally valid but
substantively circular claim.

## Formal objects and adversary boundary

`MRAP/Protocol.lean` defines:

- a finite set of protocol roles and actions;
- a typed `Step role action before after` relation whose constructors are the
  only legal transitions;
- protocol state containing the release identity, predecessor and committed
  registry heads, evidence gates, authorization facts, deployment bindings and
  modelled time;
- `Reachable initial current`, the reflexive-transitive closure of `Step` from
  an `Initial` state; and
- `AuthorizationIntegrity`, the invariant enforced over every reachable trace.

`MRAP/Security.lean` defines:

- a symbolic envelope carrying role, action, release, artifact, interface,
  expected registry head, nonce, issue time, expiry and an authenticated flag;
- an acceptance context with the current bindings, clock, used nonces and a
  known-compromise predicate;
- `EnvelopeAdmissible`, which requires authentication, authorization, exact
  bindings, freshness and a live interval; and
- `AuthenticatedStep` and `AuthenticatedReachable`, which compose admissible
  envelopes with lifecycle transitions and record the consumed nonce.

`MRAP/Deployment.lean` defines:

- an ideal current-record registry with an append-only head, monotone sequence,
  used-nonce set, and atomic `commit` operation;
- an authorization record and receipt bound to release, artifact, interface,
  predecessor head, sequence, expiry, nonce, gate result, and status;
- an atomic `activate` operation that checks the current authorized record,
  remeasured artifact/interface identifiers, and a lease bounded by the
  authorization deadline;
- `CanServe`, which rechecks the live current record, exact gateway binding,
  observed head and sequence, requested artifact/interface, lease, and
  authorization expiry on every abstract request; and
- `RealizesActive`, an explicit relation between a reachable lifecycle
  `ACTIVE` state and a serving ideal registry/gateway state.

The environment is nondeterministic: it may choose any enabled step, including
a concurrent external registry commit, monitoring time update, suspension,
expiry, revocation or abort. It cannot construct a step for an unpermitted
role/action pair, forge an authorization, mutate a frozen release identity, or
bypass a constructor precondition. Those exclusions define the abstraction's
security boundary; they are not conclusions about a real identity provider,
signature library, gateway or registry implementation.

Here `authenticated = true` is a symbolic premise representing successful
verification by an approved cryptographic implementation. Known-compromised
roles are rejected and replayed nonces cannot be accepted. The model does not
prove Ed25519, key generation, certificate validation, compromise detection or
security after an unknown key compromise.

## Machine-checked theorem set

| Claim ID | Lean declaration | Checked statement |
|---|---|---|
| `FV-AUTH-1` | `reachable_authorization_integrity` | Every reachable state satisfies `AuthorizationIntegrity`. |
| `FV-AUTH-2` | `active_implies_committed_clear_and_bound` | An active reachable state has all registered gates, request, commit, authorization, changed head, exact artifact/interface binding and unexpired modelled time. |
| `FV-ID-1` | `step_preserves_release_identity` | Every protocol step preserves the registered artifact, interface and predecessor head. |
| `FV-TERM-1` | `terminal_release_phase_is_absorbing` | No constructible step moves a terminal release back to a nonterminal phase. |
| `FV-RBAC-1` | `every_step_is_role_authorized` | Every protocol transition is permitted for its indexed role and action. |
| `FV-CAS-1` | `stale_head_second_commit_fails` | After a successful compare-and-swap strictly advances an append-only head, another commit using the old expected head fails. |
| `FV-REG-1` | `reachable_registry_head_never_decreases` | Registry heads never decrease on any reachable trace, excluding ABA head reuse in the abstract model. |
| `FV-NONVAC-1` | `valid_active_trace_exists` | A concrete trace satisfying every constructor premise reaches `ACTIVE`, so authorization integrity is not vacuous. |
| `FV-DEP-COMMIT-1` | `commit_succeeds_iff_admissible`, `successful_commit_is_atomic_and_bound` | Ideal commit succeeds exactly for admissible requests; every success advances the sequence, writes the exact bound authorization and receipt, consumes the nonce, clears the registered gates, and is live at commit time. |
| `FV-DEP-COMMIT-2` | `committed_request_replay_is_rejected`, `used_nonce_commit_is_rejected`, `stale_concurrent_commit_is_rejected` | Replaying the committed request, reusing any consumed nonce, or committing another request against its stale predecessor is rejected. |
| `FV-DEP-ACT-1` | `activation_succeeds_iff_current_record_admissible`, `successful_activation_can_serve`, `can_serve_implies_current_live_bound_authorization` | Ideal activation succeeds exactly when the current record and measurements are admissible; success yields a serving state, and every serving state has a current active, gate-cleared, release-bound authorization and live bounded lease. |
| `FV-DEP-BIND-1` | `artifact_substitution_cannot_be_served`, `interface_substitution_cannot_be_served`, `stale_gateway_cannot_serve` | Artifact/interface substitution and a gateway observing a non-current head cannot serve. |
| `FV-DEP-TIME-1` | `expired_lease_cannot_serve`, `authorization_deadline_cannot_serve` | An expired gateway lease or authorization deadline cannot serve. |
| `FV-DEP-STOP-1` | `revocation_stops_existing_gateway`, `suspension_stops_existing_gateway` | Revocation or suspension advances registry state and invalidates the existing gateway. |
| `FV-DEP-REAL-1` | `reachable_active_has_serving_realization`, `ideal_commit_and_activation_are_executable` | Every reachable unexpired active lifecycle state has a serving ideal realization, and a concrete commit–activate–serve execution is kernel checked. |
| `FV-MSG-1` | `successful_acceptance_is_authenticated_authorized_and_bound` | Every accepted envelope is authenticated, uncompromised, role-authorized, release/artifact/interface/head-bound and unexpired. |
| `FV-MSG-2` | `accepted_envelope_replay_is_rejected` | Acceptance records the nonce and the same envelope is rejected on replay. |
| `FV-MSG-3` | `mismatched_artifact_is_rejected`, `compromised_signer_is_rejected`, `expired_envelope_is_rejected` | Binding mismatch, known compromise and expiry each force rejection. |
| `FV-COMP-1` | `authenticated_step_requires_a_bound_message` | Every authenticated lifecycle step has one admissible, fresh envelope which is recorded as used. |
| `FV-COMP-2` | `authenticated_reachable_projects` | Every authenticated trace projects to a trace of the lifecycle transition system. |
| `FV-COMP-3` | `authenticated_reachable_authorization_integrity`, `authenticated_active_implies_committed_clear_and_bound` | The authorization invariant and active-state guarantee hold for the composed authenticated semantics. |
| `FV-STAT-1` | `finite_false_authorization_bound` | False-authorization mass is bounded by summed component failure mass. |
| `FV-STAT-2` | `finite_false_authorization_within_budget` | If summed component failure mass is within a budget, false-authorization mass is within it. |
| `FV-STAT-3` | `rational_experiment_false_authorization_within_budget` | The same bound holds for a normalized, positive-denominator finite rational experiment with a budget no larger than one. |
| `FV-STAT-4` | `registered_component_budget_controls_false_authorization` | Individually justified component masses reconcile to the failure table, fit their allocations, and collectively control false authorization under the registered total budget. |
| `FV-MUT-1` | `direct_unsafe_activation_is_rejected` | A concrete active state lacking gates, commit and correct binding violates the invariant. |

The formal statistical claim uses a finite outcome list. Each outcome has a
natural-number weight and a list of component-failure indicators. Choosing a
positive common denominator \(D\) represents any finite rational distribution:

\[
  \Pr(A)=D^{-1}\sum_x w_x\mathbf 1_A(x).
\]

For false authorization event \(A\) and registered failure events \(F_i\), the
`SoundOutcome.sound` field encodes the critical adequacy premise
\(A\subseteq\bigcup_iF_i\). Lean proves the cross-multiplied form

\[
  \sum_x w_x\mathbf 1_A(x)
  \leq
  \sum_i\sum_x w_x\mathbf 1_{F_i}(x)
  \leq B.
\]

Dividing by \(D>0\) gives the probability statement. The proof does not create
the adequacy premise, validate a data-generating model, or show that a chosen
test really has its advertised error rate. Those obligations must be supplied
by the preregistered statistical design and its scientific justification.

`RegisteredBudgetExperiment` makes the budget ledger inspectable: each
`ComponentClaim` contains a failure mass, an allocation and a proof that the
former fits the latter; `ledgerExact` reconciles the claimed masses to the
failure table; the allocations must fit the total budget; and the total budget
must fit the experiment denominator. These are proof-carrying premises. The
Lean theorem verifies their arithmetic consequence, while the assurance case
must justify that each empirical family really corresponds to its registered
failure event and coverage claim.

## Reproduction and proof hygiene

The package is under [`../formal/lean/`](../formal/lean/) and pins
`leanprover/lean4:v4.32.1`. It has no Mathlib or other package dependency.

```bash
python scripts/verify_formal_protocol.py
```

The wrapper rebuilds the package, checks the exact Lean version, rejects
`sorry`/`admit` placeholders, runs `#print axioms` on every public claim and
permits only `propext` and `Quot.sound`. CI additionally audits the compiled
Lean environment, so a hidden custom axiom or transitive `sorryAx` fails the
build. The negative witnesses are compiled as theorems; they are not a
substitute for the universal invariant proof.

The trusted computing base for these checks comprises the Lean kernel and its
logical foundations, the toolchain/build path used to produce and run it, and
the computing platform. Tactics may generate proof terms, but the kernel checks
those terms. Reviewers should reproduce the check from the pinned source and
record the repository commit and toolchain digest in an assurance case.

## Correspondence and explicit non-claims

The Python `ReleaseProtocolRun` verifier follows the same lifecycle vocabulary.
Its `authenticated_v1` profile verifies domain-separated, release-bound
Ed25519 signatures for every event and declared artifact against an external
trust store, rejects supplied compromised-key identifiers, and enforces a
strictly increasing registry sequence. The machine-readable
[`../formal/protocol-correspondence-v1.json`](../formal/protocol-correspondence-v1.json)
and its regression test fail when roles, phases, event/action mappings or role
permissions drift silently. The [adversarial mutation evaluation](protocol-evaluation.md)
then checks concrete Python rejection behavior.

These controls narrow the correspondence gap, but this is **not a refinement proof**
of the Lean transition system. They do not establish semantic
equivalence between Pydantic parsing, canonicalization, Python replay and Lean
evaluation. The ideal deployment specification likewise gives a precise
software target, not evidence that a concrete database or gateway implements
it. Until parser-to-semantics and implementation-to-deployment refinements are
supplied, the formal result applies directly only to the Lean model.

In particular, the machine-checked core:

- does not prove that a released model is safe, private, fair, useful, lawful or
  robust;
- does not prove policy or threat-model completeness, truth of evidence, or the
  adequacy premise \(A\subseteq\bigcup_iF_i\);
- does not formally verify signature, hash, canonicalization, registry or
  gateway implementations, worker, monitor, Python, PostgreSQL, network, or
  deployment platform (the ideal registry/gateway semantics are verified, but
  concrete implementations and the Python mutation tests are not Lean proofs
  of refinement);
- does not prove liveness, distributed availability, universal composability,
  real-time clock fidelity, reliable compromise detection, or security after
  an unknown key compromise; and
- does not turn an offline assessment into a production authorization.

These are open assurance obligations, not informal consequences of the Lean
proof.
