import MRAP.Protocol
import Std.Tactic

/-!
# Ideal registry and gateway deployment

This module formalizes the mathematically relevant deployment boundary.  It is
an ideal functionality: atomicity, durable state, authentic observations and
faithful execution are semantic premises.  No database, network, operating
system or cryptographic implementation is claimed to be verified here.
-/

namespace MRAP.Deployment

inductive AuthorizationStatus where
  | authorized
  | active
  | suspended
  | revoked
  | expired
  deriving DecidableEq, Repr

structure AuthorizationRecord where
  release : Nat
  artifact : Nat
  interface : Nat
  predecessorHead : Nat
  committedHead : Nat
  sequence : Nat
  expiresAt : Nat
  nonce : Nat
  gatesClear : Bool
  status : AuthorizationStatus
  deriving DecidableEq, Repr

structure RegistryState where
  head : Nat
  sequence : Nat
  record : Option AuthorizationRecord
  usedNonces : List Nat
  deriving DecidableEq, Repr

structure CommitRequest where
  release : Nat
  artifact : Nat
  interface : Nat
  expectedHead : Nat
  expectedSequence : Nat
  newHead : Nat
  expiresAt : Nat
  nonce : Nat
  gatesClear : Bool
  deriving DecidableEq, Repr

structure AuthorizationReceipt where
  release : Nat
  artifact : Nat
  interface : Nat
  oldHead : Nat
  newHead : Nat
  sequence : Nat
  expiresAt : Nat
  nonce : Nat
  deriving DecidableEq, Repr

structure CommitResult where
  registry : RegistryState
  receipt : AuthorizationReceipt
  deriving DecidableEq, Repr

def CommitAdmissible
    (registry : RegistryState)
    (request : CommitRequest)
    (now : Nat) : Prop :=
  request.expectedHead = registry.head ∧
  request.expectedSequence = registry.sequence ∧
  registry.head < request.newHead ∧
  request.nonce ∉ registry.usedNonces ∧
  request.gatesClear = true ∧
  now < request.expiresAt

instance commitAdmissibleDecidable
    (registry : RegistryState)
    (request : CommitRequest)
    (now : Nat) : Decidable (CommitAdmissible registry request now) := by
  unfold CommitAdmissible
  infer_instance

def committedRecord
    (registry : RegistryState)
    (request : CommitRequest) : AuthorizationRecord := {
  release := request.release
  artifact := request.artifact
  interface := request.interface
  predecessorHead := registry.head
  committedHead := request.newHead
  sequence := registry.sequence + 1
  expiresAt := request.expiresAt
  nonce := request.nonce
  gatesClear := request.gatesClear
  status := .authorized
}

def commit
    (registry : RegistryState)
    (request : CommitRequest)
    (now : Nat) : Option CommitResult :=
  if CommitAdmissible registry request now then
    let record := committedRecord registry request
    some {
      registry := {
        head := request.newHead
        sequence := registry.sequence + 1
        record := some record
        usedNonces := request.nonce :: registry.usedNonces
      }
      receipt := {
        release := request.release
        artifact := request.artifact
        interface := request.interface
        oldHead := registry.head
        newHead := request.newHead
        sequence := registry.sequence + 1
        expiresAt := request.expiresAt
        nonce := request.nonce
      }
    }
  else
    none

theorem successful_commit_is_admissible
    {registry : RegistryState}
    {request : CommitRequest}
    {now : Nat}
    {result : CommitResult}
    (hsuccess : commit registry request now = some result) :
    CommitAdmissible registry request now := by
  unfold commit at hsuccess
  split at hsuccess
  next hadmissible => exact hadmissible
  next => contradiction

theorem commit_succeeds_iff_admissible
    {registry : RegistryState}
    {request : CommitRequest}
    {now : Nat} :
    (∃ result, commit registry request now = some result) ↔
      CommitAdmissible registry request now := by
  constructor
  · rintro ⟨result, hsuccess⟩
    exact successful_commit_is_admissible hsuccess
  · intro hadmissible
    unfold commit
    simp only [if_pos hadmissible]
    exact ⟨_, rfl⟩

theorem successful_commit_is_atomic_and_bound
    {registry : RegistryState}
    {request : CommitRequest}
    {now : Nat}
    {result : CommitResult}
    (hsuccess : commit registry request now = some result) :
    result.registry.head = request.newHead ∧
    result.registry.sequence = registry.sequence + 1 ∧
    result.registry.record = some (committedRecord registry request) ∧
    request.nonce ∈ result.registry.usedNonces ∧
    result.receipt.oldHead = registry.head ∧
    result.receipt.newHead = result.registry.head ∧
    result.receipt.sequence = result.registry.sequence ∧
    request.expectedHead = registry.head ∧
    request.expectedSequence = registry.sequence ∧
    registry.head < result.registry.head ∧
    request.gatesClear = true ∧
    now < request.expiresAt := by
  have hadmissible := successful_commit_is_admissible hsuccess
  unfold commit at hsuccess
  split at hsuccess
  next =>
    simp only [Option.some.injEq] at hsuccess
    subst result
    rcases hadmissible with
      ⟨hhead, hsequence, hadvance, _hfresh, hgates, hexpires⟩
    exact ⟨rfl, rfl, rfl, by simp, rfl, rfl, rfl, hhead, hsequence,
      hadvance, hgates, hexpires⟩
  next => contradiction

theorem committed_request_replay_is_rejected
    {registry : RegistryState}
    {request : CommitRequest}
    {now : Nat}
    {result : CommitResult}
    (hsuccess : commit registry request now = some result) :
    commit result.registry request now = none := by
  have hproperties := successful_commit_is_atomic_and_bound hsuccess
  rcases hproperties with
    ⟨hnewHead, _hnewSequence, _hrecord, _hnonce, _holdHead, _hrhead,
      _hrsequence, hexpected, _hexpectedSequence, hadvance, _hgates, _hexpires⟩
  unfold commit
  split
  next hadmissible =>
    have hsame : request.expectedHead = result.registry.head := hadmissible.1
    have hcontradiction : registry.head = result.registry.head :=
      hexpected.symm.trans hsame
    exact (Nat.ne_of_lt hadvance hcontradiction).elim
  next => rfl

theorem used_nonce_commit_is_rejected
    {registry : RegistryState}
    {request : CommitRequest}
    {now : Nat}
    (hused : request.nonce ∈ registry.usedNonces) :
    commit registry request now = none := by
  unfold commit
  split
  next hadmissible =>
    exact (hadmissible.2.2.2.1 hused).elim
  next => rfl

theorem stale_concurrent_commit_is_rejected
    {registry : RegistryState}
    {first second : CommitRequest}
    {now : Nat}
    {result : CommitResult}
    (hsuccess : commit registry first now = some result)
    (hsameHead : second.expectedHead = first.expectedHead) :
    commit result.registry second now = none := by
  have hproperties := successful_commit_is_atomic_and_bound hsuccess
  rcases hproperties with
    ⟨hnewHead, _hnewSequence, _hrecord, _hnonce, _holdHead, _hrhead,
      _hrsequence, hexpected, _hexpectedSequence, hadvance, _hgates, _hexpires⟩
  unfold commit
  split
  next hadmissible =>
    have hsecond : second.expectedHead = result.registry.head := hadmissible.1
    have hcontradiction : registry.head = result.registry.head :=
      hexpected.symm.trans (hsameHead.symm.trans hsecond)
    exact (Nat.ne_of_lt hadvance hcontradiction).elim
  next => rfl

structure GatewayState where
  enabled : Bool
  release : Nat
  artifact : Nat
  interface : Nat
  observedHead : Nat
  observedSequence : Nat
  leaseUntil : Nat
  deriving DecidableEq, Repr

structure ActivationReceipt where
  release : Nat
  artifact : Nat
  interface : Nat
  registryHead : Nat
  registrySequence : Nat
  activatedAt : Nat
  leaseUntil : Nat
  deriving DecidableEq, Repr

structure ActivationResult where
  registry : RegistryState
  gateway : GatewayState
  receipt : ActivationReceipt
  deriving DecidableEq, Repr

def ActivationAdmissible
    (registry : RegistryState)
    (record : AuthorizationRecord)
    (measuredArtifact measuredInterface now leaseUntil : Nat) : Prop :=
  registry.record = some record ∧
  record.status = .authorized ∧
  record.gatesClear = true ∧
  record.committedHead = registry.head ∧
  record.sequence = registry.sequence ∧
  measuredArtifact = record.artifact ∧
  measuredInterface = record.interface ∧
  now < leaseUntil ∧
  leaseUntil ≤ record.expiresAt

instance activationAdmissibleDecidable
    (registry : RegistryState)
    (record : AuthorizationRecord)
    (measuredArtifact measuredInterface now leaseUntil : Nat) :
    Decidable (ActivationAdmissible registry record measuredArtifact
      measuredInterface now leaseUntil) := by
  unfold ActivationAdmissible
  infer_instance

def activate
    (registry : RegistryState)
    (measuredArtifact measuredInterface now leaseUntil : Nat) :
    Option ActivationResult :=
  match registry.record with
  | none => none
  | some record =>
      if ActivationAdmissible registry record measuredArtifact
          measuredInterface now leaseUntil then
        let activeRecord := { record with status := .active }
        some {
          registry := { registry with record := some activeRecord }
          gateway := {
            enabled := true
            release := record.release
            artifact := record.artifact
            interface := record.interface
            observedHead := registry.head
            observedSequence := registry.sequence
            leaseUntil := leaseUntil
          }
          receipt := {
            release := record.release
            artifact := record.artifact
            interface := record.interface
            registryHead := registry.head
            registrySequence := registry.sequence
            activatedAt := now
            leaseUntil := leaseUntil
          }
        }
      else
        none

theorem activation_succeeds_iff_current_record_admissible
    {registry : RegistryState}
    {measuredArtifact measuredInterface now leaseUntil : Nat} :
    (∃ result,
      activate registry measuredArtifact measuredInterface now leaseUntil =
        some result) ↔
    ∃ record,
      ActivationAdmissible registry record measuredArtifact measuredInterface
        now leaseUntil := by
  constructor
  · rintro ⟨result, hsuccess⟩
    unfold activate at hsuccess
    split at hsuccess
    next => contradiction
    next record _hrecord =>
      split at hsuccess
      next hadmissible => exact ⟨record, hadmissible⟩
      next => contradiction
  · rintro ⟨record, hadmissible⟩
    unfold activate
    rw [hadmissible.1]
    simp only [if_pos hadmissible]
    exact ⟨_, rfl⟩

def CanServe
    (registry : RegistryState)
    (gateway : GatewayState)
    (now requestedArtifact requestedInterface : Nat) : Prop :=
  ∃ record : AuthorizationRecord,
    registry.record = some record ∧
    record.status = .active ∧
    record.gatesClear = true ∧
    record.committedHead = registry.head ∧
    record.sequence = registry.sequence ∧
    gateway.enabled = true ∧
    gateway.release = record.release ∧
    gateway.artifact = record.artifact ∧
    gateway.interface = record.interface ∧
    gateway.observedHead = registry.head ∧
    gateway.observedSequence = registry.sequence ∧
    requestedArtifact = gateway.artifact ∧
    requestedInterface = gateway.interface ∧
    now < gateway.leaseUntil ∧
    gateway.leaseUntil ≤ record.expiresAt

instance canServeDecidable
    (registry : RegistryState)
    (gateway : GatewayState)
    (now requestedArtifact requestedInterface : Nat) :
    Decidable (CanServe registry gateway now requestedArtifact requestedInterface) := by
  unfold CanServe
  infer_instance

theorem successful_activation_can_serve
    {registry : RegistryState}
    {measuredArtifact measuredInterface now leaseUntil : Nat}
    {result : ActivationResult}
    (hsuccess :
      activate registry measuredArtifact measuredInterface now leaseUntil =
        some result) :
    CanServe result.registry result.gateway now measuredArtifact measuredInterface := by
  unfold activate at hsuccess
  split at hsuccess
  next => contradiction
  next record hrecord =>
    split at hsuccess
    next hadmissible =>
      simp only [Option.some.injEq] at hsuccess
      subst result
      rcases hadmissible with
        ⟨_hrecord, _hstatus, hgates, hhead, hsequence, hartifact,
          hinterface, hlease, hexpires⟩
      refine ⟨{ record with status := .active }, rfl, rfl, hgates, ?_, ?_,
        rfl, rfl, rfl, rfl, rfl, rfl, ?_, ?_, hlease, hexpires⟩
      · exact hhead
      · exact hsequence
      · exact hartifact
      · exact hinterface
    next => contradiction

theorem can_serve_implies_current_live_bound_authorization
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hserve : CanServe registry gateway now requestedArtifact requestedInterface) :
    ∃ record : AuthorizationRecord,
      registry.record = some record ∧
      record.status = .active ∧
      record.gatesClear = true ∧
      record.committedHead = registry.head ∧
      record.sequence = registry.sequence ∧
      requestedArtifact = record.artifact ∧
      requestedInterface = record.interface ∧
      gateway.observedHead = registry.head ∧
      gateway.observedSequence = registry.sequence ∧
      now < gateway.leaseUntil ∧
      gateway.leaseUntil ≤ record.expiresAt := by
  rcases hserve with
    ⟨record, hrecord, hstatus, hgates, hhead, hsequence, _henabled,
      _hrelease, hartifact, hinterface, hobservedHead, hobservedSequence,
      hrequestedArtifact, hrequestedInterface, hlease, hexpires⟩
  exact ⟨record, hrecord, hstatus, hgates, hhead, hsequence,
    hrequestedArtifact.trans hartifact, hrequestedInterface.trans hinterface,
    hobservedHead, hobservedSequence, hlease, hexpires⟩

theorem artifact_substitution_cannot_be_served
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hmismatch : requestedArtifact ≠ gateway.artifact) :
    ¬ CanServe registry gateway now requestedArtifact requestedInterface := by
  intro hserve
  rcases hserve with ⟨_, _, _, _, _, _, _, _, _, _, _, _, hbinding, _, _, _⟩
  exact hmismatch hbinding

theorem interface_substitution_cannot_be_served
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hmismatch : requestedInterface ≠ gateway.interface) :
    ¬ CanServe registry gateway now requestedArtifact requestedInterface := by
  intro hserve
  rcases hserve with ⟨_, _, _, _, _, _, _, _, _, _, _, _, _, hbinding, _, _⟩
  exact hmismatch hbinding

theorem stale_gateway_cannot_serve
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hstale : gateway.observedHead ≠ registry.head) :
    ¬ CanServe registry gateway now requestedArtifact requestedInterface := by
  intro hserve
  rcases hserve with ⟨_, _, _, _, _, _, _, _, _, _, hhead, _, _, _, _, _⟩
  exact hstale hhead

theorem expired_lease_cannot_serve
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hexpired : gateway.leaseUntil ≤ now) :
    ¬ CanServe registry gateway now requestedArtifact requestedInterface := by
  intro hserve
  rcases hserve with ⟨_, _, _, _, _, _, _, _, _, _, _, _, _, _, hlive, _⟩
  omega

theorem authorization_deadline_cannot_serve
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hdeadline :
      ∀ record, registry.record = some record → record.expiresAt ≤ now) :
    ¬ CanServe registry gateway now requestedArtifact requestedInterface := by
  intro hserve
  rcases hserve with
    ⟨record, hrecord, _, _, _, _, _, _, _, _, _, _, _, _, hlease, hexpires⟩
  have hrecordExpired := hdeadline record hrecord
  omega

def changeStatus
    (registry : RegistryState)
    (release : Nat)
    (status : AuthorizationStatus) : RegistryState :=
  match registry.record with
  | none => registry
  | some record =>
      if record.release = release then {
        head := registry.head + 1
        sequence := registry.sequence + 1
        record := some { record with status := status }
        usedNonces := registry.usedNonces
      } else
        registry

def revoke (registry : RegistryState) (release : Nat) : RegistryState :=
  changeStatus registry release .revoked

def suspend (registry : RegistryState) (release : Nat) : RegistryState :=
  changeStatus registry release .suspended

theorem status_change_stops_existing_gateway
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    {status : AuthorizationStatus}
    (hserve : CanServe registry gateway now requestedArtifact requestedInterface) :
    ¬ CanServe (changeStatus registry gateway.release status) gateway now
      requestedArtifact requestedInterface := by
  rcases hserve with
    ⟨record, hrecord, _hstatus, _hgates, _hcommitted, _hsequence, _henabled,
      hrelease, _hartifact, _hinterface, hobserved, _hobservedSequence,
      _hrequestedArtifact, _hrequestedInterface, _hlease, _hexpires⟩
  intro hchanged
  have hreleaseEq : record.release = gateway.release := hrelease.symm
  have hbound := can_serve_implies_current_live_bound_authorization hchanged
  rcases hbound with
    ⟨_newRecord, _hnewRecord, _hnewStatus, _hnewGates, _hnewCommitted,
      _hnewSequence, _hnewRequestedArtifact, _hnewRequestedInterface,
      hnewObservedHead, _hnewObservedSequence, _hnewLease, _hnewExpires⟩
  unfold changeStatus at hnewObservedHead
  rw [hrecord] at hnewObservedHead
  simp only [hreleaseEq, ↓reduceIte] at hnewObservedHead
  rw [hobserved] at hnewObservedHead
  omega

theorem revocation_stops_existing_gateway
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hserve : CanServe registry gateway now requestedArtifact requestedInterface) :
    ¬ CanServe (revoke registry gateway.release) gateway now
      requestedArtifact requestedInterface := by
  exact status_change_stops_existing_gateway hserve

theorem suspension_stops_existing_gateway
    {registry : RegistryState}
    {gateway : GatewayState}
    {now requestedArtifact requestedInterface : Nat}
    (hserve : CanServe registry gateway now requestedArtifact requestedInterface) :
    ¬ CanServe (suspend registry gateway.release) gateway now
      requestedArtifact requestedInterface := by
  exact status_change_stops_existing_gateway hserve

/- The following relation connects an active lifecycle state to the ideal
registry/gateway state it denotes.  It is an abstract refinement relation, not
a claim about Python or a concrete service implementation. -/
def RealizesActive
    (protocol : State)
    (registry : RegistryState)
    (gateway : GatewayState)
    (release sequence nonce : Nat) : Prop :=
  protocol.phase = .active ∧
  registry.head = protocol.committedHead ∧
  registry.sequence = sequence ∧
  registry.record = some {
    release := release
    artifact := protocol.artifact
    interface := protocol.interface
    predecessorHead := protocol.registeredHead
    committedHead := protocol.committedHead
    sequence := sequence
    expiresAt := protocol.expiresAt
    nonce := nonce
    gatesClear := true
    status := .active
  } ∧
  gateway = {
    enabled := true
    release := release
    artifact := protocol.artifact
    interface := protocol.interface
    observedHead := protocol.committedHead
    observedSequence := sequence
    leaseUntil := protocol.expiresAt
  }

theorem reachable_active_has_serving_realization
    {initial protocol : State}
    (hreachable : Reachable initial protocol)
    (hactive : protocol.phase = .active)
    (release sequence nonce : Nat) :
    ∃ registry gateway,
      RealizesActive protocol registry gateway release sequence nonce ∧
      CanServe registry gateway protocol.clock protocol.artifact
        protocol.interface := by
  have hintegrity := active_implies_committed_clear_and_bound hreachable hactive
  rcases hintegrity with
    ⟨hacceptable, _hrequested, _hcas, _hauthorized, _hhead,
      _hartifact, _hinterface, hexpires⟩
  rcases hacceptable with
    ⟨_hevidence, _hcoverage, _hcontrols, _hassessment, _hselection⟩
  let record : AuthorizationRecord := {
    release := release
    artifact := protocol.artifact
    interface := protocol.interface
    predecessorHead := protocol.registeredHead
    committedHead := protocol.committedHead
    sequence := sequence
    expiresAt := protocol.expiresAt
    nonce := nonce
    gatesClear := true
    status := .active
  }
  let registry : RegistryState := {
    head := protocol.committedHead
    sequence := sequence
    record := some record
    usedNonces := [nonce]
  }
  let gateway : GatewayState := {
    enabled := true
    release := release
    artifact := protocol.artifact
    interface := protocol.interface
    observedHead := protocol.committedHead
    observedSequence := sequence
    leaseUntil := protocol.expiresAt
  }
  refine ⟨registry, gateway, ?_, ?_⟩
  · simp [RealizesActive, registry, gateway, record, hactive]
  · refine ⟨record, ?_⟩
    simp [registry, gateway, record, hexpires]

def exampleRegistry : RegistryState := {
  head := 30
  sequence := 7
  record := none
  usedNonces := []
}

def exampleRequest : CommitRequest := {
  release := 1
  artifact := 10
  interface := 20
  expectedHead := 30
  expectedSequence := 7
  newHead := 31
  expiresAt := 10
  nonce := 99
  gatesClear := true
}

theorem ideal_commit_and_activation_are_executable :
    ∃ committed activated,
      commit exampleRegistry exampleRequest 0 = some committed ∧
      activate committed.registry 10 20 0 5 = some activated ∧
      CanServe activated.registry activated.gateway 0 10 20 := by
  let committed : CommitResult := {
    registry := {
      head := 31
      sequence := 8
      record := some (committedRecord exampleRegistry exampleRequest)
      usedNonces := [99]
    }
    receipt := {
      release := 1
      artifact := 10
      interface := 20
      oldHead := 30
      newHead := 31
      sequence := 8
      expiresAt := 10
      nonce := 99
    }
  }
  let activeRecord : AuthorizationRecord := {
    committedRecord exampleRegistry exampleRequest with
    status := .active
  }
  let activated : ActivationResult := {
    registry := { committed.registry with record := some activeRecord }
    gateway := {
      enabled := true
      release := 1
      artifact := 10
      interface := 20
      observedHead := 31
      observedSequence := 8
      leaseUntil := 5
    }
    receipt := {
      release := 1
      artifact := 10
      interface := 20
      registryHead := 31
      registrySequence := 8
      activatedAt := 0
      leaseUntil := 5
    }
  }
  refine ⟨committed, activated, ?_, ?_, ?_⟩ <;>
    decide

end MRAP.Deployment
