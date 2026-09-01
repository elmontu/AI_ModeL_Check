# Model-governance core

MRAP is an institutional model-governance protocol. Its primary question is:

> Under what documented conditions may an institution authorize, operate,
> change, suspend, and retire a particular model and complete release interface?

The answer is not produced by a risk score, payoff table, or equilibrium. It is
produced by a controlled decision process with named authority, accountable
ownership, non-compensable evidence requirements, independent challenge,
affected-party consideration, recorded reasons, exact deployment binding, and
lifecycle enforcement.

## Governance functions

The governance core requires an institution to:

1. **Define legitimate purpose and scope.** Register the intended use,
   prohibited uses, recipients, affected populations, protected units, model
   family, complete interface, jurisdictions, and authorization lifetime.
2. **Assign decision rights and accountability.** Name the model owner, policy
   authority, data/population steward, independent assessor, authorizing
   authority, registry, operator, monitor, and incident/retirement authority.
3. **Control conflicts of interest.** Separate evidence production,
   assessment, authorization, and operation as required by the trust profile;
   disclose any permitted role concentration.
4. **Freeze requirements before results.** Bind the policy, threat catalogue,
   candidate set, evidence plan, statistical budget, utility floor, and
   governance approvals before outcome-dependent selection.
5. **Require non-compensable evidence.** Privacy, safety, security, fairness,
   legality, utility, population, transfer, and portfolio requirements are
   conjunctive. A favorable result cannot purchase an override of an unrelated
   failed mandatory gate.
6. **Support challenge and contestation.** Preserve adverse findings,
   objections, dissent, decision reasons, conditions, and reassessment. A new
   decision creates a new immutable instance rather than rewriting history.
7. **Bind authorization to deployment.** Approval covers only the exact model
   bytes, components, preprocessing, interface, controls, recipients,
   population, purpose, registry state, and time period reviewed.
8. **Govern the full lifecycle.** Monitor conditions, cumulative exposure,
   drift, incidents, use changes, and control failure; suspend, revoke,
   reassess, or retire when the authorization predicates cease to hold.

## Four-layer architecture

| Layer | Question | Decision effect |
|---|---|---|
| Governance core | Is the institutional decision legitimate, accountable, contestable, and within authority? | Defines who may decide and the mandatory process |
| Assurance evidence | Do registered privacy, safety, security, fairness, utility, legal, and operational claims have adequate evidence? | May clear, block, or leave individual gates inconclusive |
| Strategic stress tests | Could conflicts, selective disclosure, weak review effort, risk externalization, or non-credible enforcement undermine the arrangement? | Advisory defense in depth; cannot authorize or override a gate |
| Technical enforcement | Is the authorized artifact/interface actually what is deployed, monitored, suspended, and revoked? | Enforces the bounded authorization |

Game theory belongs only in the third layer. It can expose a weak institutional
arrangement, but it cannot establish legal authority, procedural legitimacy,
affected-party acceptability, distributive justice, or substantive model
safety.

## Governance invariants and implementation boundary

The normative protocol aims to preserve:

- **authority:** only the designated authority can commit an authorization;
- **non-bypass:** every mandatory gate and approval precedes authorization;
- **separation:** roles cannot exercise prohibited powers or silently approve
  their own evidence;
- **reasoned traceability:** evidence, dissent, decisions, conditions, failures,
  incidents, and retirement remain linked and auditable;
- **binding:** authorization names the exact release and complete interface;
- **temporality:** authorization expires and material changes require a new
  instance; and
- **remedy:** suspension and revocation stop future authorized service, while
  prior disclosure remains part of the incident record.

The Lean core machine-checks a narrower subset: role-indexed transition
authorization, required gate/commit predecessors, compare-and-swap freshness,
artifact/interface binding, expiry, suspension, revocation, and an ideal
registry/gateway functionality. It does not machine-check whether a governance
purpose is legitimate, affected parties were adequately represented, the
policy is complete, an assessor is institutionally independent, or a remedy is
fair and effective.

## Strategic supplement

The exact-rational `strategic_assurance` library is a supplemental stress test.
Its problem record now binds the accountable model owner, decision authority,
independent review body, affected-party groups, governance objective,
conflict-of-interest controls, contestation process, and incident/retirement
authority.

Its certificate deliberately contains:

```text
governance_decision_effect = none
authorization_effect = none
hard_gate_effect = cannot_override_or_remove
```

`registered_model_status` reports what follows inside the declared payoff and
uncertainty model. `deployment_evidence_status` reports whether the parameter
evidence is eligible for real-world interpretation. Neither field is a
governance verdict. Authorization remains a separate registry transition after
all mandatory governance and assurance requirements pass.
