# Post-critique design-control validation

This retained evaluation runs twelve named regression cases covering interface
completeness, future timestamps, policy-governed selection, evidence
disposition, manifest interface binding, audit-ledger identity/splicing,
registry sequence/head replay, runtime identity, and CLI domain outcomes. It
also records the binary64 boundary counterexample that keeps MRAP G7 open.

Reproduce from the repository root:

```bash
PYTHONPATH=src python scripts/evaluate_design_controls.py \
  --output reproduction/design-control-validation/results.json
```

The result contains raw case counts and test identifiers. It deliberately has
no safety score. Passing the enumerated cases is not release authorization,
scientific validation, a production-registry test, or a trusted-build
attestation.
