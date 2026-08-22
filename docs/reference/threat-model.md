# Service threat model

## Assets

- private training data and protected person, household, organization, establishment, device, transaction, event, or custom-unit membership;
- submitted model artifacts and preprocessing state;
- raw attack and accountant evidence;
- release contracts, thresholds, reports, approvals, and audit history;
- signing keys and verifier trust roots; and
- the integrity of `clear / block / inconclusive` decisions.

## Actors

- data owner submits the release package;
- analyzer workers process potentially hostile artifacts;
- assessor reviews evidence and assumptions;
- approver accepts or rejects the governance action;
- release operator serves only an authorized artifact/interface;
- recipient may be honest, curious, compromised, or colluding; and
- infrastructure administrator may be separately trusted or corrupt according to deployment policy.

## Default adversary knowledge

The implemented version-1 assessment always assumes that the recipient knows:

- the complete database and feature schema, including column names, order, types, semantics, target definition, row/class counts, missingness, and feature cardinalities;
- for every numeric feature, exact minimum, maximum, range, mean, median, standard deviation, variance, first and third quartiles, interquartile range, and median absolute deviation;
- for every categorical feature and target class, the complete domain plus exact counts and frequencies; and
- the candidate record and its non-secret fields in a membership game.

The conservative empirical profile supplies both full-source and exact target-training summaries. These summaries are auxiliary knowledge in the game and are also supplied to the no-model baseline. If the metadata is transferred with the artifact, it is additionally part of the release package and artifact hash.

The request schema does not accept a weaker profile. Any future weaker profile would require a separately named, versioned policy and schema change, external justification, and reassessment; it cannot be selected by a submitter in the current framework.

Summary knowledge is not silently upgraded to row-level microdata, an identity roster, or an independently observed target signal. Conversely, exact extrema, medians, and small-cell counts may themselves leak membership or attributes, so they cannot be dismissed as harmless documentation.

## Trust boundaries

The decision core accepts inert JSON only. Model parsing and empirical attacks occur outside it in sandboxed workers. The core verifies artifact and evidence hashes, validates contracts, calculates evidence brackets, persists an audit event, and optionally signs the report manifest. Production identity, storage, queue, and KMS services are separate trusted components.

Optimization requests declare a trust profile. `cooperative` treats hash-bound submissions as accountable assertions and is appropriate only where the submitting authority is trusted not to fabricate evidence. `separated_assessor` requires an allowlisted Ed25519-signed assessment. `adversarial_supply_chain` is rejected by the current core because artifact correctness would require sandboxed independent replay and attestation. These profiles are not interchangeable assurance levels.

## Primary threats and controls

| Threat | Core control | Required deployment control |
|---|---|---|
| Artifact substitution | SHA-256 binding and signed manifest | canonical upload, immutable storage, malware scan, release-time hash check |
| Evidence substitution or rebinding | complete source payload plus pre-analysis release/policy/artifact/interface/population/game context | worker attestation, immutable logs, approved adapter images |
| Metric confusion | machine-readable decision metric | policy review and versioned metric catalogue |
| Population-scope substitution | threat/analyzer scope identifiers and signed request/report binding | authoritative scope registry, dated population evidence, profile approval |
| Missing evidence treated as safe | fail-closed trivial ceiling | UI must preserve `inconclusive` without override-by-default |
| Malicious model deserialization | no model loading in core | no-network sandbox, non-root worker, format allowlist, resource quotas |
| Accountant misstatement | scope and replay requirements | independent accountant adapter and sealed training ledger |
| Audit tampering | hash-chained local events | append-only store, external anchoring, backup and restore verification |
| Signing-key theft | signature verification support | HSM/KMS, dual control, rotation and revocation |
| Stale approval | report and final-manifest expiry, versioned population snapshots, expiring controls | release gateway expiry and revocation enforcement |
| Portfolio race | signed portfolio-registry head plus replayed joint experiment per mandatory population-secret pair | transactionally locked portfolio register, compare-and-swap commit, and joint reassessment |
| Summary-metadata leakage | bind declared summaries into auxiliary knowledge and compare metadata-only with model-plus-metadata attacks | metadata inventory, exact-value review, minimisation/rounding, and reassessment of the modified package |
| Baseline-confounded inference | paired controlled-inference contract, same-side-information comparator, exact multiplicity-adjusted floor | pre-register secret/metric, retain paired raw cells, verify ground truth and reconstruction membership |
| Partial DP scope | accountant ceiling clears only with replay, protected-unit match, and complete mechanism scope | privatize or compose preprocessing, selection, stopping, calibration, summaries, and correlated releases |
| Invalid population generalization | population evidence remains scope-bound; finite-count certificates require a probability design | dated frame, inclusion probabilities, coverage/nonresponse analysis, weights, subgroup precision, and drift checks |
| Evaluated/released interface substitution | optimizer requires identical experiment identifiers or a replayed garbling in the direction `assessed dominates released` | release gateway binds the approved artifact, interface, precision, query budget, and control configuration |
| False information-dominance claim | stochastic kernel, dimensions, state space, scope, and row total-variation reconstruction residual are replayed | independent experiment-construction review and conformance fixtures |
| Universal-risk scalarization | privacy remains a vector of mandatory constraints; unknown Blackwell relations remain incomparable | policy may choose among feasible configurations only after threats, metrics, and tolerances are fixed |
| Population-anchor substitution | released and assessed experiment bindings require the same ordered state space and prior | authoritative dated population profile, subgroup review, and reassessment on drift |
| Control theatre | a privacy-credited control must change the information structure and have enforcement evidence | technical gateway enforcement, configuration attestation, monitoring, and expiry |
| Premise substitution | canonical decision-game, population, artifact, and complete-interface hashes on evidence and decisions | independent assessor review of experiment construction and source coverage |
| Utility substitution | utility certificate binds configuration, artifact, interface, population snapshots, and evaluation split | immutable split registry and reproducible utility worker |
| Search theatre | `reject` requires a hash-bound enumeration certificate | approved configuration generator and independently replayed completeness certificate |
| Interactive LLM under-modelling | complete LLM protocol contract is accepted but cannot clear through one-shot analyzers | transcript-level accountant/interactive-channel analyzer covering tools, RAG, memory, updates, and concurrency |
| Unsupported model-family coercion | 20-category catalog routes unknown families to custom review and never clears | approve family-specific workers and modality/protocol threat profiles |

## Explicit non-claims

The current core does not prove confidentiality of infrastructure, correctness of external analyzer software, accuracy or completeness of a population definition/model, transferability across populations, completeness of a candidate-configuration search without an enumeration certificate, interactive LLM safety, or UC realization of a release protocol. A verified garbling or joint-portfolio certificate is only as faithful as the finite experiments supplied to it. Hash chaining detects modification only relative to a trusted anchor; deleting the latest unanchored database state can otherwise evade local verification. Production must anchor chain heads and atomically compare portfolio heads in separately protected services.
