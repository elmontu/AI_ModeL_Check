# Model Release Assurance 0.6 update

This corrigendum updates the supplied 0.5.0 framework specification after the code audit, XGBoost and LLM research review, and the cumulative synthetic-health release experiment. The original finite decision theory remains unchanged. The implementation and claim boundary are refreshed below.

## Corrected implementation claim

Version 0.6 is an offline, architecture-neutral assurance compiler with a fail-safe final gate. It can describe and route all governed model families, but it has model-specific evidence workers for only a subset. It is not an accredited service and does not authorize every listed family.

The assessment request/report contract is version 3.0. This is a breaking change because source-observed evidence context cannot be safely inferred from a v2 record after collection.

The following corrections are now implemented:

- analyzer sources bind the complete framework-owned payload rather than a claimant-selected subset;
- every analyzer payload carries a source-observed evidence context containing release-contract, policy, artifact, interface, population and decision-game hashes plus observation time;
- the engine verifies that context before analysis and analyzers copy it into evidence records without post-analysis restamping;
- signed assessment manifests bind the complete request and exact report timestamps/expiry;
- low-FPR membership floors use simultaneous one-sided bounds and refuse unattainable operating points;
- the XGBoost worker binds deterministic splits, training, runtime, attack game, raw scores and replayable cache evidence;
- the LLM watermark/canary profile has strict hypothesis, null-calibration, query-budget, key, tokenizer, randomization, attack and provenance checks while retaining `can_clear: false`; and
- a 20-category all-model catalog now routes classical, neural, multimodal, generative, composite and agentic systems.

## Revised model-family statement

The architecture-independent core is universal only in contract semantics:

\[
\text{release contract} + \text{decision game} + \text{typed evidence} +
\text{portfolio} + \text{utility} + \text{binding}.
\]

Evidence remains family-, modality- and interface-specific. A null tabular membership attack cannot clear a vision model; a one-shot LLM extraction test cannot clear an adaptive RAG/tool service; and an API test cannot represent full artifact access. Unknown families and unsupported interactive protocols fail closed.

The complete executable matrix is in [model-family coverage](model-family-coverage.md).

## Revised portfolio statement

The supplied synthetic Singapore health study strengthens the framework's portfolio motivation. Multiple models trained on the same protected roster produced higher membership and diabetes-attribute attack success under the declared interface. This does not estimate real-patient risk, but it is a concrete witness that model count and combined outputs can change the attack channel.

The study's referenced data, runner and retained artifacts were not included in this repository. Version 0.6 therefore treats its numerical results as supplied findings, not independently replayed local evidence.

Accordingly, `previous_release_ids` is not descriptive metadata. Production assessment must resolve those identifiers against an atomic registry and assess the joint population–secret–interface portfolio. Separate assessments of individual models are insufficient when outputs can be combined.

## Current implementation status

| Layer | Status in 0.6 |
|---|---|
| Release, policy, population and threat contracts | Implemented |
| Source-originated evidence context | Implemented and tested |
| Evidence direction and fail-closed decisions | Implemented |
| All-model classification and coverage review | Implemented; never clears |
| Tree linkage and DP replay | Implemented for declared premises |
| Generic attack and controlled-inference floors | Implemented for predictive, non-interactive releases |
| XGBoost local screening worker | Implemented; screen only |
| LLM watermark/canary preregistration | Implemented; linter only |
| Dedicated vision/audio/graph/recommender/generative-media/RL workers | Required |
| Interactive LLM transcript assurance | Required; clearance refused |
| Production identity, KMS/HSM, immutable evidence, registry and gateway | Required |

## Remaining high-priority work

1. Add numeric prior validation for finite-secret DP ceilings or implement a proved arbitrary-prior bound.
2. Replace clearance-boundary floating-point comparisons with outward interval/rational arithmetic or a certified decision margin.
3. Replay the configuration generator before allowing a certified exhaustive `reject`.
4. Add independently operated interface inventory and positive-control workers.
5. Implement modality-specific workers in risk order rather than claiming universal empirical coverage.
6. Connect `previous_release_ids` to a transactionally locked portfolio registry.
7. Build production trust infrastructure and obtain external accreditation.

## Revised conclusion

MRA now has an explicit path for all model families and closes the previously identified evidence-rebinding defect. Its defensible promise is routing and fail-closed assurance, not universal clearance. A model can be considered only when its exact release surface, family-specific threats, cumulative portfolio and source-bound evidence are complete. Unsupported families remain visible and inconclusive instead of being forced through an invalid XGBoost or generic-attack template.
