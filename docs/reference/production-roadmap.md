# Production roadmap

## Target operating model

The target is an accredited, whole-of-government capability that accepts model-release packages, runs approved analyzers in isolation, evaluates evidence for every mandatory threat, selects a supportable release configuration, and issues a signed authorization bound to the committed portfolio state.

The same core may support person, household, organization, programme, device, transaction, event, and custom protected units. Profiles must not treat those populations as statistically interchangeable.

## Work package 1: governance and policy

Deliver:

- named service owner, data owner, assessor, approver, and release operator;
- central threat catalogue and mandatory-evidence rules;
- central, domain, adopter, and release-contract policy layers;
- deterministic profile resolution with provenance for every override;
- independently owned tolerances and utility requirements; and
- expiry, revocation, exception, appeal, incident, and records-management processes.

Exit gate: threats, tolerances, and utility requirements are frozen independently of candidate results.

## Work package 2: trusted core integration

Deliver:

- immutable artifact and evidence storage;
- approved analyzer catalogue with version pinning;
- independent replay for accountants and certificates;
- canonical population and interface registries;
- complete configuration enumeration where `reject` is permitted; and
- conformance fixtures for evidence direction, substitution, and portfolio handling.

Exit gate: every analyzer passes positive controls, malformed-input tests, scope-binding tests, and replay tests.

## Work package 3: service security

Deliver:

- OIDC authentication, RBAC/ABAC, four-eyes approval, and separation of duties;
- no-network, non-root analyzer sandboxes with resource limits;
- malware scanning and format allowlists for submitted artifacts;
- HSM/KMS-backed signing, rotation, and revocation;
- encrypted storage, retention, legal hold, deletion, backup, and restore controls;
- idempotent jobs, retry policy, cancellation, and concurrency limits; and
- metrics, structured logs, traces, alerting, and incident runbooks.

Exit gate: penetration test, restore exercise, load test, and operational-readiness review are approved.

## Work package 4: atomic portfolio registry

Deliver a registry that:

- identifies every mandatory population-secret pair;
- stores the committed release transcript and remaining budgets;
- supports transactionally locked read-evaluate-commit operations;
- rejects stale registry heads and replayed authorizations;
- supports revocation and reassessment; and
- exports independently verifiable history.

Exit gate: concurrency tests show that no two releases can both authorize against the same stale state.

## Work package 5: population and mechanism validation

Deliver:

- authoritative, dated population frames and protected-unit definitions;
- inclusion, coverage, nonresponse, subgroup-precision, and drift checks;
- validated contribution bounds for grouped units;
- complete private-pipeline accounting, including preprocessing and correlated outputs;
- stronger domain-specific attacks with positive controls; and
- transcript-level analysis for interactive LLM services.

Exit gate: evidence is representative of the intended adopter, population, interface, and operating conditions.

## Work package 6: multi-domain pilot and accreditation

Pilot at least three materially different scopes, including a large person population, a smaller cohort, and an organization-focused case. Exercise artifact substitution, evidence substitution, population drift, stale contracts, accountant mismatch, attack non-attainment, concurrent releases, revocation, and emergency refusal.

Exit gate: independent security, statistical, legal, and operational reviewers approve the shared core and each adopter approves its profile and residual-risk register.

## Non-negotiable controls

1. Unknown contract fields fail validation.
2. Artifact, evidence, policy, or configuration hash mismatch stops processing.
3. Every evidence record declares its scope, assumptions, metric, and direction.
4. Attack failure never becomes a clearance upper bound.
5. Population size never becomes an anonymity guarantee.
6. A changed release surface requires direct reassessment or verified safe reduction.
7. `unassessed` portfolio dependence cannot clear.
8. Utility is enforced before disclosure minimization.
9. Final authorization is bound to configuration, population snapshots, registry head, trust profile, and expiry.
10. Interactive LLM services require transcript-level assurance.
11. Floating-point optimization may propose a result; exact or outward-rounded replay must verify clearance-critical certificates.
