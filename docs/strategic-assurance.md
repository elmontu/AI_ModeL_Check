# Executable strategic governance stress test

The `strategic_assurance` library implements the exact-rational, one-shot
incentive stress tests in Section 5 of the mathematical foundations. It is an
optional supplement to the [model-governance core](governance-core.md), not the
governance protocol itself. It evaluates:

- robust submitter compliance under uncertain detection, consequence, and
  violation gain;
- high versus low assessor effort under an observable validation contract;
- attacker effort versus abstention after information value, cost, detection,
  and enforceable consequence are registered; and
- Blackwell-safe control improvement when a valid garbling certificate is
  combined with a non-smaller non-information attack burden.

It is a design-time diagnostic engine. It does not determine legitimate
purpose, institutional authority, affected-party acceptability, accountability,
contestation, distributive fairness, or social welfare. It does not estimate
human behaviour, calibrate sanctions, authorize a release, or replace any MRAP
hard gate.

Every problem must bind its governance context: accountable model owner,
decision authority, independent review body, affected-party groups, governance
objective, conflict-of-interest controls, contestation process, and
incident/retirement authority. This records where the stress test sits; it does
not mathematically validate those institutional arrangements.

## Exact and fail-closed semantics

Every input endpoint is a canonical rational number. A numerical interval must
name an evidence record, claim identifier, and unit. Detection and validation
probabilities additionally require a positive-control identifier. The problem
is rejected when evidence is missing, does not support the named claim, uses
the wrong unit, or postdates the assessment. Deployment-eligible evidence must
also bind a SHA-256 source digest. The digest establishes source identity, not
the truth or external validity of its contents.

The engine uses rectangular uncertainty sets and adverse endpoints:

- `supported`: the required positive margin holds for every parameter tuple;
- `contradicted`: no parameter tuple can attain the required margin; and
- `inconclusive`: the interval crosses the margin or a behavioral premise is
  unavailable.

Follower ties are pessimistic. Equality at zero never establishes unique
compliance or abstention. Unenforceable consequences must be encoded as exactly
zero, so monitoring cannot acquire fictional deterrence credit.

The certificate reports two aggregate statuses. `registered_model_status`
describes only the registered interval problem. `deployment_evidence_status`
additionally fails closed on incomplete actor types, unobservable commitment,
and evidence marked ineligible for deployment. Synthetic assumptions can
therefore validate code and algebra but cannot become deployment evidence.

Neither status is a governance verdict. Every certificate fixes
`governance_decision_effect` and `authorization_effect` to `none`, and
`hard_gate_effect` to `cannot_override_or_remove`.

## Library use

```python
from pathlib import Path

from model_release_assurance.strategic_assurance import (
    StrategicAssuranceProblem,
    solve_strategic_assurance,
    verify_strategic_assurance,
)

problem = StrategicAssuranceProblem.model_validate_json(
    Path("reproduction/strategic-assurance/config.json").read_text()
)
certificate = solve_strategic_assurance(
    problem,
    certificate_id="local-strategic-certificate",
)
verification = verify_strategic_assurance(problem, certificate)
assert verification.valid
```

Certificate replay recomputes the problem digest and every exact interval. A
changed status, bound, or input fails verification.

## Reproducible synthetic experiment

Run the preregistered stress test with:

```bash
python scripts/run_strategic_assurance_experiment.py
```

The default configuration samples 10,000 rational parameter tuples for each of
five claims using seed `20260825`. In the retained configuration:

| Claim | Exact interval status | Sampled tuples meeting the strict margin |
|---|---|---:|
| adverse-result omission deterrence | supported | 10,000 / 10,000 |
| control-shortcut deterrence | supported | 10,000 / 10,000 |
| assessor high effort | supported | 10,000 / 10,000 |
| registered-recipient attack abstention | supported | 10,000 / 10,000 |
| anonymous external attack abstention | contradicted | 0 / 10,000 |

The anonymous-attacker result is the important negative control. Its
consequence is unenforceable and therefore zero. Sweeping detection probability
from zero to one leaves its payoff unchanged. A public or cross-border endpoint
must instead reduce information, stop access, or raise actual attack cost.

Sampling is a regression check, not the proof: the exact interval endpoints
establish the certificate. The experiment uses explicitly synthetic SGD values
and probabilities. Its registered-model status is `contradicted` because of
the anonymous-attacker negative control, while its deployment-evidence status
is `inconclusive`. Its governance decision is explicitly `not_evaluated`; none
of these results describes a real hospital, attacker, or jurisdiction.

## Verification

```bash
PYTHONPATH=src python -m unittest \
  tests.test_strategic_assurance \
  tests.test_strategic_assurance_experiment -v
```

The tests include certificate tampering, unsupported provenance, unit mismatch,
missing positive controls, favorable ties, incomplete types, hidden commitment,
conflicted independent review, unenforceable sanctions, non-risk-neutral
behavior, and invalid Blackwell transfer.
