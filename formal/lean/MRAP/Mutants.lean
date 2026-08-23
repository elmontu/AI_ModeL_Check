import MRAP.Protocol

/-!
This file contains executable negative witnesses.  Each witness represents a
mutation that would be unsafe if admitted as a protocol transition; Lean checks
that it violates the proved invariant.
-/

namespace MRAP.Mutants

def unauthorizedActive : State where
  phase := .active
  artifact := 10
  interface := 20
  registeredHead := 30
  registryHead := 30
  committedHead := 30
  deployedArtifact := 99
  deployedInterface := 98
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

theorem direct_unsafe_activation_is_rejected :
    ¬ AuthorizationIntegrity unauthorizedActive := by
  simp [AuthorizationIntegrity, RegisteredAcceptable, unauthorizedActive]

def staleRegistry : Registry := { head := 7 }

theorem stale_compareAndSwap_is_rejected :
    compareAndSwap staleRegistry 6 8 = none := by
  decide

theorem monitoring_authority_cannot_commit :
    permitted .monitoringAuthority .commitAuthorization = false := by
  decide

end MRAP.Mutants
