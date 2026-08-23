import Std.Tactic

/-!
# MRAP authorization-integrity model

This file defines the executable transition relation used for the machine-checked
MRAP security claim.  It deliberately proves authorization integrity for the
registered predicates; it does not assert that those predicates completely
characterize real-world model safety.
-/

namespace MRAP

inductive Role where
  | modelOwner
  | policyAuthority
  | populationSteward
  | configurationGenerator
  | independentAssessor
  | evidenceAuthority
  | optimizationAuthority
  | authorizationAuthority
  | portfolioRegistry
  | deploymentGateway
  | monitoringAuthority
  | incidentAuthority
  deriving DecidableEq, Repr

inductive Action where
  | register
  | freezePlan
  | closeEvidence
  | assess
  | optimize
  | redesign
  | reject
  | submitAuthorization
  | commitAuthorization
  | externalCommit
  | activate
  | monitor
  | suspend
  | expire
  | revoke
  | abort
  deriving DecidableEq, Repr

def permitted : Role → Action → Bool
  | .modelOwner, .register => true
  | .modelOwner, .abort => true
  | .independentAssessor, .freezePlan => true
  | .independentAssessor, .assess => true
  | .independentAssessor, .abort => true
  | .evidenceAuthority, .closeEvidence => true
  | .optimizationAuthority, .optimize => true
  | .optimizationAuthority, .redesign => true
  | .optimizationAuthority, .reject => true
  | .authorizationAuthority, .submitAuthorization => true
  | .authorizationAuthority, .revoke => true
  | .authorizationAuthority, .expire => true
  | .authorizationAuthority, .abort => true
  | .portfolioRegistry, .commitAuthorization => true
  | .portfolioRegistry, .externalCommit => true
  | .portfolioRegistry, .abort => true
  | .deploymentGateway, .activate => true
  | .deploymentGateway, .expire => true
  | .monitoringAuthority, .monitor => true
  | .monitoringAuthority, .suspend => true
  | .incidentAuthority, .suspend => true
  | .incidentAuthority, .revoke => true
  | _, _ => false

inductive Phase where
  | draft
  | registered
  | planFrozen
  | evidenceFrozen
  | assessed
  | optimized
  | commitPending
  | authorized
  | active
  | suspended
  | redesignRequired
  | rejected
  | expired
  | revoked
  | aborted
  deriving DecidableEq, Repr

def Phase.isTerminal : Phase → Bool
  | .redesignRequired | .rejected | .expired | .revoked | .aborted => true
  | _ => false

def Phase.hasLiveAuthorization : Phase → Bool
  | .authorized | .active | .suspended => true
  | _ => false

structure State where
  phase : Phase
  artifact : Nat
  interface : Nat
  registeredHead : Nat
  registryHead : Nat
  committedHead : Nat
  deployedArtifact : Nat
  deployedInterface : Nat
  planFrozen : Bool
  evidenceComplete : Bool
  selectionCoverage : Bool
  controlsPass : Bool
  assessmentClear : Bool
  selectionReleasable : Bool
  authorizationRequested : Bool
  casCommitted : Bool
  authorizationIssued : Bool
  expiresAt : Nat
  clock : Nat
  deriving DecidableEq, Repr

def Initial (s : State) : Prop :=
  s.phase = .draft ∧
  s.registeredHead = s.registryHead ∧
  s.committedHead = s.registeredHead ∧
  s.planFrozen = false ∧
  s.evidenceComplete = false ∧
  s.selectionCoverage = false ∧
  s.controlsPass = false ∧
  s.assessmentClear = false ∧
  s.selectionReleasable = false ∧
  s.authorizationRequested = false ∧
  s.casCommitted = false ∧
  s.authorizationIssued = false

inductive Step : Role → Action → State → State → Prop where
  | register
      (hphase : s.phase = .draft) :
      Step .modelOwner .register s { s with phase := .registered }
  | freezePlan
      (hphase : s.phase = .registered) :
      Step .independentAssessor .freezePlan s
        { s with phase := .planFrozen, planFrozen := true }
  | closeEvidence
      (complete coverage controls : Bool)
      (hphase : s.phase = .planFrozen)
      (hplan : s.planFrozen = true)
      (hunauthorized : s.authorizationIssued = false) :
      Step .evidenceAuthority .closeEvidence s {
        s with
        phase := .evidenceFrozen
        evidenceComplete := complete
        selectionCoverage := coverage
        controlsPass := controls
      }
  | assessClear
      (hphase : s.phase = .evidenceFrozen)
      (hcomplete : s.evidenceComplete = true)
      (hcoverage : s.selectionCoverage = true)
      (hcontrols : s.controlsPass = true) :
      Step .independentAssessor .assess s
        { s with phase := .assessed, assessmentClear := true }
  | assessNonClear
      (hphase : s.phase = .evidenceFrozen)
      (hunauthorized : s.authorizationIssued = false) :
      Step .independentAssessor .assess s
        { s with phase := .assessed, assessmentClear := false }
  | optimizeRelease
      (hphase : s.phase = .assessed)
      (hclear : s.assessmentClear = true) :
      Step .optimizationAuthority .optimize s
        { s with phase := .optimized, selectionReleasable := true }
  | requireRedesign
      (hphase : s.phase = .assessed)
      (hunauthorized : s.authorizationIssued = false) :
      Step .optimizationAuthority .redesign s
        { s with phase := .redesignRequired, selectionReleasable := false }
  | reject
      (hphase : s.phase = .assessed)
      (hunauthorized : s.authorizationIssued = false)
      (_exhaustiveSearchReplayed : True) :
      Step .optimizationAuthority .reject s
        { s with phase := .rejected, selectionReleasable := false }
  | submitAuthorization
      (expiry : Nat)
      (hphase : s.phase = .optimized)
      (hcomplete : s.evidenceComplete = true)
      (hcoverage : s.selectionCoverage = true)
      (hcontrols : s.controlsPass = true)
      (hclear : s.assessmentClear = true)
      (hreleasable : s.selectionReleasable = true)
      (hfresh : s.clock < expiry) :
      Step .authorizationAuthority .submitAuthorization s {
        s with
        phase := .commitPending
        authorizationRequested := true
        expiresAt := expiry
      }
  | commitAuthorization
      (newHead : Nat)
      (hphase : s.phase = .commitPending)
      (hrequested : s.authorizationRequested = true)
      (hcomplete : s.evidenceComplete = true)
      (hcoverage : s.selectionCoverage = true)
      (hcontrols : s.controlsPass = true)
      (hclear : s.assessmentClear = true)
      (hreleasable : s.selectionReleasable = true)
      (hhead : s.registryHead = s.registeredHead)
      (hadvance : s.registryHead < newHead)
      (hfresh : s.clock < s.expiresAt) :
      Step .portfolioRegistry .commitAuthorization s {
        s with
        phase := .authorized
        registryHead := newHead
        committedHead := newHead
        casCommitted := true
        authorizationIssued := true
      }
  | externalCommit
      (newHead : Nat)
      (hadvance : s.registryHead < newHead) :
      Step .portfolioRegistry .externalCommit s { s with registryHead := newHead }
  | activate
      (hphase : s.phase = .authorized)
      (hauthorized : s.authorizationIssued = true)
      (hcas : s.casCommitted = true)
      (hfresh : s.clock < s.expiresAt) :
      Step .deploymentGateway .activate s {
        s with
        phase := .active
        deployedArtifact := s.artifact
        deployedInterface := s.interface
      }
  | monitorContinue
      (now : Nat)
      (hphase : s.phase = .active)
      (hmonotone : s.clock ≤ now)
      (hfresh : now < s.expiresAt) :
      Step .monitoringAuthority .monitor s { s with clock := now }
  | suspend
      (role : Role)
      (hrole : permitted role .suspend = true)
      (hphase : s.phase = .active) :
      Step role .suspend s { s with phase := .suspended }
  | expire
      (role : Role)
      (hrole : permitted role .expire = true)
      (now : Nat)
      (hlive : s.phase.hasLiveAuthorization = true)
      (hmonotone : s.clock ≤ now)
      (hexpired : s.expiresAt ≤ now) :
      Step role .expire s { s with phase := .expired, clock := now }
  | revokeAuthorized
      (role : Role)
      (hrole : permitted role .revoke = true)
      (hphase : s.phase = .authorized) :
      Step role .revoke s { s with phase := .revoked }
  | revokeActive
      (role : Role)
      (hrole : permitted role .revoke = true)
      (hphase : s.phase = .active) :
      Step role .revoke s { s with phase := .revoked }
  | revokeSuspended
      (role : Role)
      (hrole : permitted role .revoke = true)
      (hphase : s.phase = .suspended) :
      Step role .revoke s { s with phase := .revoked }
  | abortRegistered
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .registered) :
      Step role .abort s { s with phase := .aborted }
  | abortPlanned
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .planFrozen) :
      Step role .abort s { s with phase := .aborted }
  | abortEvidence
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .evidenceFrozen) :
      Step role .abort s { s with phase := .aborted }
  | abortAssessed
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .assessed) :
      Step role .abort s { s with phase := .aborted }
  | abortOptimized
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .optimized) :
      Step role .abort s { s with phase := .aborted }
  | abortPending
      (role : Role)
      (hrole : permitted role .abort = true)
      (hphase : s.phase = .commitPending) :
      Step role .abort s { s with phase := .aborted }

inductive Reachable (initial : State) : State → Prop where
  | initial (h : Initial initial) : Reachable initial initial
  | next
      (hprevious : Reachable initial s)
      (hstep : Step role action s t) :
      Reachable initial t

def RegisteredAcceptable (s : State) : Prop :=
  s.evidenceComplete = true ∧
  s.selectionCoverage = true ∧
  s.controlsPass = true ∧
  s.assessmentClear = true ∧
  s.selectionReleasable = true

def AuthorizationIntegrity (s : State) : Prop :=
  (s.phase = .active →
    RegisteredAcceptable s ∧
    s.authorizationRequested = true ∧
    s.casCommitted = true ∧
    s.authorizationIssued = true ∧
    s.committedHead ≠ s.registeredHead ∧
    s.deployedArtifact = s.artifact ∧
    s.deployedInterface = s.interface ∧
    s.clock < s.expiresAt) ∧
  (s.authorizationIssued = true →
    RegisteredAcceptable s ∧
    s.authorizationRequested = true ∧
    s.casCommitted = true ∧
    s.committedHead ≠ s.registeredHead) ∧
  (s.casCommitted = true → s.authorizationRequested = true)

theorem initial_authorization_integrity
    {s : State} (hinitial : Initial s) : AuthorizationIntegrity s := by
  rcases hinitial with
    ⟨hphase, _hhead, _hcommitted, _hplan, _hevidence, _hcoverage,
      _hcontrols, _hassessment, _hselection, hrequested, hcas, hauthorized⟩
  simp [AuthorizationIntegrity, hphase, hrequested, hcas, hauthorized]

theorem step_preserves_authorization_integrity
    {role : Role} {action : Action} {s t : State}
    (hinvariant : AuthorizationIntegrity s)
    (hstep : Step role action s t) :
    AuthorizationIntegrity t := by
  cases hstep <;>
    simp_all [AuthorizationIntegrity, RegisteredAcceptable, Phase.hasLiveAuthorization] <;>
    omega

theorem reachable_authorization_integrity
    {initial current : State}
    (hreachable : Reachable initial current) :
    AuthorizationIntegrity current := by
  induction hreachable with
  | initial hinitial => exact initial_authorization_integrity hinitial
  | next _ hstep ih => exact step_preserves_authorization_integrity ih hstep

theorem active_implies_committed_clear_and_bound
    {initial current : State}
    (hreachable : Reachable initial current)
    (hactive : current.phase = .active) :
    RegisteredAcceptable current ∧
    current.authorizationRequested = true ∧
    current.casCommitted = true ∧
    current.authorizationIssued = true ∧
    current.committedHead ≠ current.registeredHead ∧
    current.deployedArtifact = current.artifact ∧
    current.deployedInterface = current.interface ∧
    current.clock < current.expiresAt :=
  (reachable_authorization_integrity hreachable).1 hactive

theorem step_preserves_release_identity
    {role : Role} {action : Action} {s t : State}
    (hstep : Step role action s t) :
    t.artifact = s.artifact ∧
    t.interface = s.interface ∧
    t.registeredHead = s.registeredHead := by
  cases hstep <;> simp

theorem terminal_phase_is_not_live
    {phase : Phase}
    (hterminal : phase.isTerminal = true) :
    phase.hasLiveAuthorization = false := by
  cases phase <;> simp_all [Phase.isTerminal, Phase.hasLiveAuthorization]

theorem terminal_release_phase_is_absorbing
    {role : Role} {action : Action} {s t : State}
    (hterminal : s.phase.isTerminal = true)
    (hstep : Step role action s t) :
    t.phase = s.phase := by
  have hnotlive := terminal_phase_is_not_live hterminal
  cases hstep <;> simp_all [Phase.isTerminal]

theorem every_step_is_role_authorized
    {role : Role} {action : Action} {s t : State}
    (hstep : Step role action s t) :
    permitted role action = true := by
  cases hstep <;> simp_all [permitted]

theorem registry_head_never_decreases
    {role : Role} {action : Action} {s t : State}
    (hstep : Step role action s t) :
    s.registryHead ≤ t.registryHead := by
  cases hstep <;> simp_all <;> omega

theorem reachable_registry_head_never_decreases
    {initial current : State}
    (hreachable : Reachable initial current) :
    initial.registryHead ≤ current.registryHead := by
  induction hreachable with
  | initial _ => exact Nat.le_refl _
  | next _ hstep ih =>
      exact Nat.le_trans ih (registry_head_never_decreases hstep)

structure Registry where
  head : Nat
  deriving DecidableEq, Repr

def compareAndSwap (registry : Registry) (expected newHead : Nat) : Option Registry :=
  if expected = registry.head ∧ registry.head < newHead then
    some { head := newHead }
  else
    none

theorem successful_compareAndSwap_advances
    {registry committed : Registry}
    {expected newHead : Nat}
    (hsuccess : compareAndSwap registry expected newHead = some committed) :
    expected = registry.head ∧
    committed.head = newHead ∧
    registry.head < committed.head := by
  simp only [compareAndSwap] at hsuccess
  split at hsuccess
  next hcondition =>
    simp only [Option.some.injEq] at hsuccess
    subst committed
    exact ⟨hcondition.1, rfl, hcondition.2⟩
  next => contradiction

theorem stale_head_second_commit_fails
    {registry first : Registry}
    {expected firstHead secondHead : Nat}
    (hfirst : compareAndSwap registry expected firstHead = some first) :
    compareAndSwap first expected secondHead = none := by
  have hsuccess := successful_compareAndSwap_advances hfirst
  rcases hsuccess with ⟨hexpected, hfirstHead, hadvanced⟩
  have hstale : expected ≠ first.head := by
    rw [hexpected]
    exact Nat.ne_of_lt hadvanced
  simp [compareAndSwap, hstale]

/- A concrete successful trace rules out the vacuous interpretation that the
authorization invariant holds only because `active` is unreachable.  This is
a non-vacuity witness, not a distributed-service liveness theorem. -/
def nonvacuousInitial : State where
  phase := .draft
  artifact := 10
  interface := 20
  registeredHead := 30
  registryHead := 30
  committedHead := 30
  deployedArtifact := 0
  deployedInterface := 0
  planFrozen := false
  evidenceComplete := false
  selectionCoverage := false
  controlsPass := false
  assessmentClear := false
  selectionReleasable := false
  authorizationRequested := false
  casCommitted := false
  authorizationIssued := false
  expiresAt := 0
  clock := 0

theorem valid_active_trace_exists :
    ∃ active, Reachable nonvacuousInitial active ∧ active.phase = .active := by
  let s0 := nonvacuousInitial
  let s1 : State := { s0 with phase := .registered }
  let s2 : State := { s1 with phase := .planFrozen, planFrozen := true }
  let s3 : State := {
    s2 with
    phase := .evidenceFrozen
    evidenceComplete := true
    selectionCoverage := true
    controlsPass := true
  }
  let s4 : State := { s3 with phase := .assessed, assessmentClear := true }
  let s5 : State := { s4 with phase := .optimized, selectionReleasable := true }
  let s6 : State := {
    s5 with
    phase := .commitPending
    authorizationRequested := true
    expiresAt := 10
  }
  let s7 : State := {
    s6 with
    phase := .authorized
    registryHead := 31
    committedHead := 31
    casCommitted := true
    authorizationIssued := true
  }
  let s8 : State := {
    s7 with
    phase := .active
    deployedArtifact := s7.artifact
    deployedInterface := s7.interface
  }
  have h0 : Reachable s0 s0 := Reachable.initial (by
    simp [s0, nonvacuousInitial, Initial])
  have h1 : Reachable s0 s1 := Reachable.next h0 (Step.register (by
    simp [s0, nonvacuousInitial]))
  have h2 : Reachable s0 s2 := Reachable.next h1 (Step.freezePlan (by
    simp [s1]))
  have h3 : Reachable s0 s3 := Reachable.next h2 (Step.closeEvidence true true true
    (by simp [s2])
    (by simp [s2])
    (by simp [s2, s1, s0, nonvacuousInitial]))
  have h4 : Reachable s0 s4 := Reachable.next h3 (Step.assessClear
    (by simp [s3])
    (by simp [s3])
    (by simp [s3])
    (by simp [s3]))
  have h5 : Reachable s0 s5 := Reachable.next h4 (Step.optimizeRelease
    (by simp [s4])
    (by simp [s4]))
  have h6 : Reachable s0 s6 := Reachable.next h5 (Step.submitAuthorization 10
    (by simp [s5])
    (by simp [s5, s4, s3])
    (by simp [s5, s4, s3])
    (by simp [s5, s4, s3])
    (by simp [s5, s4])
    (by simp [s5])
    (by simp [s5, s4, s3, s2, s1, s0, nonvacuousInitial]))
  have h7 : Reachable s0 s7 := Reachable.next h6 (Step.commitAuthorization 31
    (by simp [s6])
    (by simp [s6])
    (by simp [s6, s5, s4, s3])
    (by simp [s6, s5, s4, s3])
    (by simp [s6, s5, s4, s3])
    (by simp [s6, s5, s4])
    (by simp [s6, s5])
    (by simp [s6, s5, s4, s3, s2, s1, s0, nonvacuousInitial])
    (by simp [s6, s5, s4, s3, s2, s1, s0, nonvacuousInitial])
    (by simp [s6, s5, s4, s3, s2, s1, s0, nonvacuousInitial]))
  have h8 : Reachable s0 s8 := Reachable.next h7 (Step.activate
    (by simp [s7])
    (by simp [s7])
    (by simp [s7])
    (by simp [s7, s6, s5, s4, s3, s2, s1, s0, nonvacuousInitial]))
  exact ⟨s8, by simpa [s0] using h8, by simp [s8]⟩

end MRAP
