import Std.Tactic

/-!
# Finite statistical error-ledger theorem

The natural-number weights below represent probability masses after choosing a
common denominator.  This is sufficient for every finite rational experiment.
The theorem proves that the mass of outcomes with any registered failure is no
greater than the sum of the component failure masses; no independence premise
is used.
-/

namespace MRAP.Statistics

def indicator (value : Bool) : Nat := if value then 1 else 0

def componentIndicatorMass (failures : List Bool) : Nat :=
  (failures.map indicator).sum

def unionIndicatorMass (failures : List Bool) : Nat :=
  indicator (failures.any id)

theorem indicator_any_le_component_sum :
    ∀ failures : List Bool,
      unionIndicatorMass failures ≤ componentIndicatorMass failures
  | [] => by simp [unionIndicatorMass, componentIndicatorMass, indicator]
  | failure :: failures => by
      cases failure with
      | false =>
          simpa [unionIndicatorMass, componentIndicatorMass, indicator] using
            indicator_any_le_component_sum failures
      | true =>
          simp [unionIndicatorMass, componentIndicatorMass, indicator]

structure Outcome where
  weight : Nat
  failures : List Bool
  deriving DecidableEq, Repr

def unionFailureMass (outcomes : List Outcome) : Nat :=
  (outcomes.map fun outcome =>
    outcome.weight * unionIndicatorMass outcome.failures).sum

def componentFailureMass (outcomes : List Outcome) : Nat :=
  (outcomes.map fun outcome =>
    outcome.weight * componentIndicatorMass outcome.failures).sum

theorem finite_weighted_union_bound (outcomes : List Outcome) :
    unionFailureMass outcomes ≤ componentFailureMass outcomes := by
  induction outcomes with
  | nil => simp [unionFailureMass, componentFailureMass]
  | cons outcome outcomes ih =>
      simp only [unionFailureMass, componentFailureMass, List.map_cons, List.sum_cons]
      exact Nat.add_le_add
        (Nat.mul_le_mul_left outcome.weight
          (indicator_any_le_component_sum outcome.failures))
        ih

structure SoundOutcome extends Outcome where
  falseAuthorization : Bool
  sound : falseAuthorization = true → failures.any id = true

def falseAuthorizationMass (outcomes : List SoundOutcome) : Nat :=
  (outcomes.map fun outcome =>
    outcome.weight * indicator outcome.falseAuthorization).sum

def soundUnionFailureMass (outcomes : List SoundOutcome) : Nat :=
  (outcomes.map fun outcome =>
    outcome.weight * unionIndicatorMass outcome.failures).sum

def soundComponentFailureMass (outcomes : List SoundOutcome) : Nat :=
  (outcomes.map fun outcome =>
    outcome.weight * componentIndicatorMass outcome.failures).sum

theorem false_authorization_indicator_le_union (outcome : SoundOutcome) :
    indicator outcome.falseAuthorization ≤ unionIndicatorMass outcome.failures := by
  cases hfalse : outcome.falseAuthorization with
  | false => simp [indicator]
  | true =>
      have hunion : outcome.failures.any id = true := outcome.sound hfalse
      simp [indicator, unionIndicatorMass, hunion]

theorem false_authorization_mass_le_union (outcomes : List SoundOutcome) :
    falseAuthorizationMass outcomes ≤ soundUnionFailureMass outcomes := by
  induction outcomes with
  | nil => simp [falseAuthorizationMass, soundUnionFailureMass]
  | cons outcome outcomes ih =>
      simp only [falseAuthorizationMass, soundUnionFailureMass,
        List.map_cons, List.sum_cons]
      exact Nat.add_le_add
        (Nat.mul_le_mul_left outcome.weight
          (false_authorization_indicator_le_union outcome))
        ih

theorem sound_union_mass_le_components (outcomes : List SoundOutcome) :
    soundUnionFailureMass outcomes ≤ soundComponentFailureMass outcomes := by
  induction outcomes with
  | nil => simp [soundUnionFailureMass, soundComponentFailureMass]
  | cons outcome outcomes ih =>
      simp only [soundUnionFailureMass, soundComponentFailureMass,
        List.map_cons, List.sum_cons]
      exact Nat.add_le_add
        (Nat.mul_le_mul_left outcome.weight
          (indicator_any_le_component_sum outcome.failures))
        ih

theorem finite_false_authorization_bound (outcomes : List SoundOutcome) :
    falseAuthorizationMass outcomes ≤ soundComponentFailureMass outcomes :=
  Nat.le_trans
    (false_authorization_mass_le_union outcomes)
    (sound_union_mass_le_components outcomes)

theorem finite_false_authorization_within_budget
    (outcomes : List SoundOutcome)
    (budget : Nat)
    (hbudget : soundComponentFailureMass outcomes ≤ budget) :
    falseAuthorizationMass outcomes ≤ budget :=
  Nat.le_trans (finite_false_authorization_bound outcomes) hbudget

/- A normalized finite rational experiment records the denominator explicitly.
The probability result remains in cross-multiplied natural-number form, so no
rounding or floating-point premise enters the proof. -/
structure RationalExperiment where
  outcomes : List SoundOutcome
  denominator : Nat
  denominatorPositive : 0 < denominator
  weightsNormalize :
    (outcomes.map fun outcome => outcome.weight).sum = denominator

structure BudgetedExperiment extends RationalExperiment where
  budgetNumerator : Nat
  budgetWithinUnit : budgetNumerator ≤ denominator
  componentMassWithinBudget :
    soundComponentFailureMass outcomes ≤ budgetNumerator

theorem rational_experiment_false_authorization_within_budget
    (experiment : BudgetedExperiment) :
    falseAuthorizationMass experiment.outcomes ≤ experiment.budgetNumerator :=
  finite_false_authorization_within_budget
    experiment.outcomes
    experiment.budgetNumerator
    experiment.componentMassWithinBudget

/- A registered component ledger exposes each statistical family's allocation
instead of assuming one opaque aggregate bound.  `ledgerExact` is the audit
obligation connecting the registered component masses to the failure table. -/
structure ComponentClaim where
  failureMass : Nat
  allocation : Nat
  withinAllocation : failureMass ≤ allocation

def claimedFailureMass (claims : List ComponentClaim) : Nat :=
  (claims.map fun claim => claim.failureMass).sum

def allocatedMass (claims : List ComponentClaim) : Nat :=
  (claims.map fun claim => claim.allocation).sum

theorem component_claims_within_allocations :
    ∀ claims : List ComponentClaim,
      claimedFailureMass claims ≤ allocatedMass claims
  | [] => by simp [claimedFailureMass, allocatedMass]
  | claim :: claims => by
      simp only [claimedFailureMass, allocatedMass, List.map_cons, List.sum_cons]
      exact Nat.add_le_add
        claim.withinAllocation
        (component_claims_within_allocations claims)

structure RegisteredBudgetExperiment extends RationalExperiment where
  componentClaims : List ComponentClaim
  ledgerExact :
    claimedFailureMass componentClaims =
      soundComponentFailureMass outcomes
  totalBudgetNumerator : Nat
  allocationsWithinTotal :
    allocatedMass componentClaims ≤ totalBudgetNumerator
  totalBudgetWithinUnit : totalBudgetNumerator ≤ denominator

theorem registered_component_budget_controls_false_authorization
    (experiment : RegisteredBudgetExperiment) :
    falseAuthorizationMass experiment.outcomes ≤
      experiment.totalBudgetNumerator := by
  have hcomponents :
      soundComponentFailureMass experiment.outcomes ≤
        allocatedMass experiment.componentClaims := by
    rw [← experiment.ledgerExact]
    exact component_claims_within_allocations experiment.componentClaims
  exact Nat.le_trans
    (finite_false_authorization_bound experiment.outcomes)
    (Nat.le_trans hcomponents experiment.allocationsWithinTotal)

end MRAP.Statistics
