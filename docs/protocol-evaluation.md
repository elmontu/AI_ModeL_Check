# Protocol adversarial evaluation

## Question

The evaluation asks whether the reference verifier rejects known unsafe
mutations while continuing to accept valid structural and authenticated
controls. It does not treat the number of test cases as a proof; the universal
abstract properties remain the Lean theorems. The mutation suite instead tests
the executable Python enforcement surface and records concrete failure modes.

## Reproduce

```bash
PYTHONPATH=src python scripts/evaluate_protocol_mutations.py \
  --output output/protocol-mutation-evaluation.json
```

The suite contains two positive controls and nineteen unsafe mutants covering:

- failed atomic commit;
- broken event hash chain;
- incomplete evidence;
- wrong artifact-producer role;
- artifact path escape;
- expired active authorization;
- cross-message payload confusion;
- unsupported rejection without exhaustive replay;
- non-increasing registry sequence;
- monitoring-authority privilege escalation;
- signed-event tampering;
- signed-artifact tampering;
- cross-release signed-message replay;
- known-compromised signer;
- signer absent from the external trust store;
- verification-profile downgrade when authenticated replay is required;
- an artifact kind belonging to another event type;
- duplicate artifact kinds within one event; and
- an expiry event before the registered deadline.

The reported mutation score is the proportion of these explicitly unsafe
variants rejected. A score of one is evidence about the enumerated mutation
classes only. It is not an estimate of total vulnerability coverage and does
not prove that model-specific scientific tests are adequate.

## Relationship to the proof

The Lean proof and mutation evaluation have different purposes. Lean proves
authorization invariants for every trace admitted by its abstract transition
relation. The mutation suite checks that selected real Python inputs are
rejected by the reference implementation. The correspondence manifest prevents
silent vocabulary and role-permission drift, but is not a refinement proof.
