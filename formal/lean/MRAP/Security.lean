import MRAP.Protocol

/-!
# Symbolic authenticated-message boundary

This module makes the message/adversary boundary explicit.  `authenticated`
abstracts successful verification by the approved cryptographic implementation;
the theorem does not prove Ed25519.  The context also rejects roles whose keys
are known to be compromised.  Unknown compromise remains outside the claim.
-/

namespace MRAP.Security

structure Envelope where
  role : Role
  action : Action
  release : Nat
  artifact : Nat
  interface : Nat
  expectedHead : Nat
  nonce : Nat
  issuedAt : Nat
  expiresAt : Nat
  authenticated : Bool
  deriving DecidableEq, Repr

structure AcceptanceContext where
  release : Nat
  artifact : Nat
  interface : Nat
  registryHead : Nat
  now : Nat
  usedNonces : List Nat
  compromised : Role → Bool

def EnvelopeAdmissible (context : AcceptanceContext) (envelope : Envelope) : Prop :=
  envelope.authenticated = true ∧
  context.compromised envelope.role = false ∧
  permitted envelope.role envelope.action = true ∧
  envelope.release = context.release ∧
  envelope.artifact = context.artifact ∧
  envelope.interface = context.interface ∧
  envelope.expectedHead = context.registryHead ∧
  envelope.nonce ∉ context.usedNonces ∧
  envelope.issuedAt ≤ context.now ∧
  context.now < envelope.expiresAt

instance envelopeAdmissibleDecidable
    (context : AcceptanceContext)
    (envelope : Envelope) : Decidable (EnvelopeAdmissible context envelope) := by
  unfold EnvelopeAdmissible
  infer_instance

def acceptEnvelope
    (context : AcceptanceContext)
    (envelope : Envelope) : Option AcceptanceContext :=
  if EnvelopeAdmissible context envelope then
    some { context with usedNonces := envelope.nonce :: context.usedNonces }
  else
    none

theorem successful_acceptance_is_admissible
    {context next : AcceptanceContext}
    {envelope : Envelope}
    (hsuccess : acceptEnvelope context envelope = some next) :
    EnvelopeAdmissible context envelope := by
  unfold acceptEnvelope at hsuccess
  split at hsuccess
  next hadmissible => exact hadmissible
  next => contradiction

theorem successful_acceptance_is_authenticated_authorized_and_bound
    {context next : AcceptanceContext}
    {envelope : Envelope}
    (hsuccess : acceptEnvelope context envelope = some next) :
    envelope.authenticated = true ∧
    context.compromised envelope.role = false ∧
    permitted envelope.role envelope.action = true ∧
    envelope.release = context.release ∧
    envelope.artifact = context.artifact ∧
    envelope.interface = context.interface ∧
    envelope.expectedHead = context.registryHead ∧
    context.now < envelope.expiresAt := by
  rcases successful_acceptance_is_admissible hsuccess with
    ⟨hauthenticated, huncompromised, hpermitted, hrelease, hartifact,
      hinterface, hhead, _hnonce, _hissued, hexpires⟩
  exact ⟨hauthenticated, huncompromised, hpermitted, hrelease, hartifact,
    hinterface, hhead, hexpires⟩

theorem successful_acceptance_records_nonce
    {context next : AcceptanceContext}
    {envelope : Envelope}
    (hsuccess : acceptEnvelope context envelope = some next) :
    envelope.nonce ∈ next.usedNonces := by
  unfold acceptEnvelope at hsuccess
  split at hsuccess
  next =>
    simp only [Option.some.injEq] at hsuccess
    subst next
    simp
  next => contradiction

theorem accepted_envelope_replay_is_rejected
    {context next : AcceptanceContext}
    {envelope : Envelope}
    (hsuccess : acceptEnvelope context envelope = some next) :
    acceptEnvelope next envelope = none := by
  have hrecorded := successful_acceptance_records_nonce hsuccess
  unfold acceptEnvelope
  split
  next hadmissible =>
    rcases hadmissible with
      ⟨_, _, _, _, _, _, _, hfresh, _, _⟩
    exact (hfresh hrecorded).elim
  next => rfl

theorem mismatched_artifact_is_rejected
    {context : AcceptanceContext}
    {envelope : Envelope}
    (hmismatch : envelope.artifact ≠ context.artifact) :
    acceptEnvelope context envelope = none := by
  unfold acceptEnvelope
  split
  next hadmissible =>
    rcases hadmissible with ⟨_, _, _, _, hartifact, _, _, _, _, _⟩
    exact (hmismatch hartifact).elim
  next => rfl

theorem compromised_signer_is_rejected
    {context : AcceptanceContext}
    {envelope : Envelope}
    (hcompromised : context.compromised envelope.role = true) :
    acceptEnvelope context envelope = none := by
  unfold acceptEnvelope
  split
  next hadmissible =>
    rcases hadmissible with ⟨_, huncompromised, _, _, _, _, _, _, _, _⟩
    simp_all
  next => rfl

theorem expired_envelope_is_rejected
    {context : AcceptanceContext}
    {envelope : Envelope}
    (hexpired : envelope.expiresAt ≤ context.now) :
    acceptEnvelope context envelope = none := by
  unfold acceptEnvelope
  split
  next hadmissible =>
    rcases hadmissible with ⟨_, _, _, _, _, _, _, _, _, hfresh⟩
    omega
  next => rfl

/-!
## Composition with the lifecycle transition system

`AuthenticatedStep` is the security boundary for an executed protocol step:
the same envelope that passes the message checks supplies the role and action
indices of the lifecycle transition.  This prevents the message theorem and
the lifecycle theorem from being two unrelated models.
-/

structure SecureState where
  protocol : State
  usedNonces : List Nat
  deriving DecidableEq, Repr

def envelopeContext
    (release : Nat)
    (compromised : Role → Bool)
    (state : SecureState) : AcceptanceContext := {
  release := release
  artifact := state.protocol.artifact
  interface := state.protocol.interface
  registryHead := state.protocol.registryHead
  now := state.protocol.clock
  usedNonces := state.usedNonces
  compromised := compromised
}

inductive AuthenticatedStep
    (release : Nat)
    (compromised : Role → Bool) : SecureState → SecureState → Prop where
  | apply
      (envelope : Envelope)
      (hadmissible :
        EnvelopeAdmissible (envelopeContext release compromised before) envelope)
      (hstep : Step envelope.role envelope.action before.protocol after.protocol)
      (hnonce : after.usedNonces = envelope.nonce :: before.usedNonces) :
      AuthenticatedStep release compromised before after

inductive AuthenticatedReachable
    (release : Nat)
    (compromised : Role → Bool)
    (initial : SecureState) : SecureState → Prop where
  | initial
      (hinitial : Initial initial.protocol) :
      AuthenticatedReachable release compromised initial initial
  | next
      (hprevious : AuthenticatedReachable release compromised initial before)
      (hstep : AuthenticatedStep release compromised before after) :
      AuthenticatedReachable release compromised initial after

theorem authenticated_step_projects
    {release : Nat}
    {compromised : Role → Bool}
    {before after : SecureState}
    (hstep : AuthenticatedStep release compromised before after) :
    ∃ role action, Step role action before.protocol after.protocol := by
  cases hstep with
  | apply envelope _ hprotocol _ =>
      exact ⟨envelope.role, envelope.action, hprotocol⟩

theorem authenticated_step_requires_a_bound_message
    {release : Nat}
    {compromised : Role → Bool}
    {before after : SecureState}
    (hstep : AuthenticatedStep release compromised before after) :
    ∃ envelope : Envelope,
      envelope.authenticated = true ∧
      compromised envelope.role = false ∧
      permitted envelope.role envelope.action = true ∧
      envelope.release = release ∧
      envelope.artifact = before.protocol.artifact ∧
      envelope.interface = before.protocol.interface ∧
      envelope.expectedHead = before.protocol.registryHead ∧
      envelope.nonce ∉ before.usedNonces ∧
      envelope.issuedAt ≤ before.protocol.clock ∧
      before.protocol.clock < envelope.expiresAt ∧
      envelope.nonce ∈ after.usedNonces := by
  cases hstep with
  | apply envelope hadmissible _ hrecorded =>
      rcases hadmissible with
        ⟨hauthenticated, huncompromised, hpermitted, hrelease, hartifact,
          hinterface, hhead, hnonce, hissued, hexpires⟩
      exact ⟨envelope, hauthenticated, huncompromised, hpermitted, hrelease,
        hartifact, hinterface, hhead, hnonce, hissued, hexpires, by
          rw [hrecorded]
          simp⟩

theorem authenticated_reachable_projects
    {release : Nat}
    {compromised : Role → Bool}
    {initial current : SecureState}
    (hreachable : AuthenticatedReachable release compromised initial current) :
    Reachable initial.protocol current.protocol := by
  induction hreachable with
  | initial hinitial => exact Reachable.initial hinitial
  | next _ hstep ih =>
      rcases authenticated_step_projects hstep with ⟨role, action, hprotocol⟩
      exact Reachable.next ih hprotocol

theorem authenticated_reachable_authorization_integrity
    {release : Nat}
    {compromised : Role → Bool}
    {initial current : SecureState}
    (hreachable : AuthenticatedReachable release compromised initial current) :
    AuthorizationIntegrity current.protocol :=
  reachable_authorization_integrity (authenticated_reachable_projects hreachable)

theorem authenticated_active_implies_committed_clear_and_bound
    {release : Nat}
    {compromised : Role → Bool}
    {initial current : SecureState}
    (hreachable : AuthenticatedReachable release compromised initial current)
    (hactive : current.protocol.phase = .active) :
    RegisteredAcceptable current.protocol ∧
    current.protocol.authorizationRequested = true ∧
    current.protocol.casCommitted = true ∧
    current.protocol.authorizationIssued = true ∧
    current.protocol.committedHead ≠ current.protocol.registeredHead ∧
    current.protocol.deployedArtifact = current.protocol.artifact ∧
    current.protocol.deployedInterface = current.protocol.interface ∧
    current.protocol.clock < current.protocol.expiresAt :=
  active_implies_committed_clear_and_bound
    (authenticated_reachable_projects hreachable)
    hactive

end MRAP.Security
