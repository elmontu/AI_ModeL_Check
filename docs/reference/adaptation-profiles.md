# Adaptation profiles

## Purpose

Model Release Assurance is a whole-of-government framework, not a health-service product. The trusted core is shared; policy, population evidence, operational integrations, and tolerances are adapted without changing the meaning of evidence or weakening fail-closed rules.

The runtime engine evaluates a single resolved, hash-bound policy bundle. Profile inheritance is a governance and policy-service operation: the resolver must retain all mandatory parent rules, record provenance for every override, and seal the effective bundle before a release submitter can reference it.

## Four layers

### 1. Whole-of-government baseline

The central baseline fixes schema rules, evidence classes, integrity controls, minimum threat coverage, separation of policy from submissions, signing requirements, audit semantics, and the rule that attack floors cannot clear a release.

### 2. Domain and population profile

This layer declares additional threats, protected-unit conventions, authoritative data sources, statistical validation, and default safeguards for a kind of population. Profiles may cover people, households, organizations/companies, establishments, devices, transactions, events, or a defined custom unit. They must specify how scope and population size are established and how often those claims expire.

### 3. Adopter profile

An agency, ministry, programme, regulator, statutory board, or participating organization identifies its legal authority, accountable roles, approved analyzers, recipient classes, risk tolerances, retention rules, and incident process. It may strengthen the baseline but cannot reinterpret an empirical floor as a ceiling or omit mandatory central threats.

### 4. Release contract

The release contract binds one artifact and interface to a recipient, purpose, model family, structured task/modality/training profile, protected unit, population scope, prior, side information, success metric, threshold, evidence, and expiry. The all-model catalog routes family-specific work but never supplies evidence. A material change creates a new assessment.

## Population patterns

| Pattern | Contract representation | Main caution |
|---|---|---|
| National or resident population | `person` or `household`, authoritative dated size bounds | rare subgroups and population drift |
| Company or organization register | `organization`, exact or bounded register size | parent/subsidiary identity and register completeness |
| Programme or service cohort | suitable unit plus explicit eligibility and reference date | selection effects and changing eligibility |
| Closed research roster | suitable unit, exact registry size, named candidate-set construction | target-signal and roster realizability |
| Open public interface | `open_dynamic`, defined reachable universe and time window | no finite-population shortcut without justification |
| Specialized unit | `custom` with a precise unit definition | ambiguity in adjacency, counting, and composition |

Population size is context, not a privacy guarantee. A large national denominator does not protect a rare subgroup, and a modeled match count does not prove anonymity. Threat games and validation must use the population actually reachable by the declared recipient.

## MOH adaptation example

MOH would supply a health-sector/adopter profile defining, for example, person or episode protected units, health-specific harms, authorised recipient classes, health-data retention controls, relevant population registers, and stricter tolerances where appropriate. The common engine, evidence semantics, cryptographic bindings, and decision rules remain unchanged. Other ministries or organization-focused programmes create parallel profiles against the same baseline.

## Change control

Central baseline changes require shared governance and compatibility review. Profile changes require the owning authority and independent assurance review. Changes to population definition, size basis, reference date, recipient, interface, protected unit, or threat tolerance invalidate reuse of the previous release decision unless an approved composition rule explicitly applies.
