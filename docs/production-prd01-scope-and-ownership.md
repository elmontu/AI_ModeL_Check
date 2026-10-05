# PRD-01: scope and ownership record

**Record:** PRD-01 / revision 0.2 / 1 October 2026.
**State:** `in_progress` — draft prepared; agency decisions and accountable owners
are pending. **Parent:** [private-cloud production plan](production-private-cloud-plan.md).
**Approval:** none recorded. This record is planning evidence, not release authority.

## Broader framework direction

The user subsequently requested broader validation using the academic research
datasets on D:, instead of fixing the implementation to healthcare. The framework
and PRD-11 engineering benchmarks are now sector-neutral. The previously selected
CDC/MOH-type agency remains an example pilot; no production agency or new private
data source is approved by this expansion. Existing decisions below describe
that pilot and remain subject to agency review.

## Confirmed direction

| Item | Recorded decision | Basis |
| --- | --- | --- |
| Hosting | Agency private cloud | User selected this option during production planning |
| Organization type | Major public-health agency, such as a CDC or Ministry of Health | User clarified the intended agency scale and mission; no particular agency or country selected |
| Data setting | Large volumes of private agency-held data | User specified this requirement; exact scale and official classification remain pending |
| Workstream | Start PRD-01: agree scope and accountable ownership | User requested task 1 |
| Repository | Government repository on D: | Existing user scope; original research and academic repositories excluded |
| Publication | Local preparation; GitHub publication pending authentication | Existing project constraint |

No specific agency name, jurisdiction, formal data classification, cloud provider,
region, agency model or named owner has been supplied. CDC and MOH are examples
of organization type, not evidence of a US or other national deployment. A workstation location
or timezone does not determine agency jurisdiction or residency requirements.

## Proposed first scope

The earlier example pilot is a **major public-health agency holding
large private datasets**. Hospital administration is not that pilot. The current
framework scope also includes other government domains and public research data.
The proposed service workflow is to audit models trained on agency-held data
and govern their release to an approved recipient, while raw data remain in
approved agency custody. The specific public-health programme, model task and
recipient have not been selected.

The roadmap proposes one agency, one tabular classifier family, one declared
recipient group and full-artifact delivery for the first accepted profile.
This limits the first model/interface, not the size of the agency or its data
architecture. The agency must agree the actual programme, model, data and
disclosure conditions. Public/synthetic assessment staging comes first;
protected-data intake and delivery remain subject to later production gates.

The currently implemented engineering fixture is **StandardScaler + GaussianNB
on bundled public breast-cancer data**, delivered as inert JSON. It demonstrates
package binding, replay and a bounded membership screen. It does not select the
agency's business use case, production model or data; its results are not agency
acceptance evidence. See the [pilot guide](red-team-export-review.md).

| Boundary | Proposed treatment for the first profile |
| --- | --- |
| Recipient access | Full model and preprocessing bytes; assume retained copies and unlimited local inspection, not an API query cap |
| Package | Exact model, fitted preprocessing, feature/class roster, dependency versions and complete relevant parent/component lineage |
| Data before approval | Bundled public/synthetic fixtures and explicitly allowlisted public research samples; no private agency data |
| Agency data access | Governed immutable dataset/snapshot references and scoped in-cloud jobs; no bulk private-data upload through the UI or export in the recipient model package |
| Scale | Large-data design requirement confirmed; row/byte counts, linkage, updates, compute and concurrency still need measured values |
| Protected-data intake | Deferred until classification, authority, custody and registration requirements are evidenced |
| Release evidence | Independent review of purpose, utility, protection claim, tests, controls, uncertainty and prior disclosure |
| Unsupported paths | New modality, model family, serving API or recipient route requires a separately accepted profile |

Proposed exclusions are multi-agency tenancy, public model distribution,
prediction-API release, regression, vision, LLM/RAG/agent interfaces,
fine-tuning/merges/ensembles and live third-party model APIs. These are first
profile exclusions, not claims that every corresponding local experiment is absent.
The agency must confirm exclusions in S09 below.

## Decisions needed to agree the scope

Use `agreed`, `pending`, or `not_applicable` with a reason and approver.
An unknown value is never an agreed default. Decision dates and references must
identify the actual accountable decision; starting this task is not that decision.

| ID | Decision | Draft value / question to resolve | Accountable role | State |
| --- | --- | --- | --- | --- |
| S01 | Agency and purpose | Organization type agreed: major public-health agency. Name/jurisdiction, public-health programme, model task, intended users/decisions, harmful errors, human review and benefit remain pending | Service owner + public-health programme owner | pending |
| S02 | Candidate and package | Production family/model/version, preprocessing, provenance and all relevant parents/components; public GaussianNB remains an engineering fixture | Service owner + statistical owner | pending |
| S03 | Data and classification | Large private agency-held data setting agreed. Dataset/version, population, source authority, sensitive fields, classification, residency, retention, repeated observations and cross-source linkage remain pending | Data owner | pending |
| S04 | Recipient and disclosure | Named recipient organization/group, purpose, full-artifact access, permitted onward use and earlier packages/outputs the recipient retains | Service owner + data owner | pending |
| S05 | Protection claim | Protected unit (person, household, encounter or other entity), linked-record contributions, attribute/membership scope, adjacency and any DP claim; feasibility belongs to PRD-13 | Data owner + statistical owner | pending |
| S06 | Utility and public-health impact | Programme metric, harmful error types, affected populations, subgroup criteria, acceptable performance/loss and omission/public-only comparator; no demo thresholds inherited | Service owner + statistical owner | pending |
| S07 | Privacy constraint | Justified tolerance or cumulative budget under S05, relevant prior disclosures and mechanism assumptions; numerical value not supplied | Policy authority + statistical owner | pending |
| S08 | Required security/privacy screens | Recipient-realistic threats, required attacks, operational blocking rules, permitted exclusions and independent review; detailed qualification in PRD-11/13 | Security owner + statistical owner | pending |
| S09 | Scope limits and reassessment | Agree first-profile exclusions, unresolved issues and triggers: changed package/data/interface/recipient/policy, new prior disclosure or invalid evidence | Service owner + security owner | pending |
| S10 | Decision authority | Accountable sponsor, four core owners below, delegation route for policy and release decisions, and independent-review conflict checks | Agency sponsor/service owner | pending |
| S11 | Scale and operating envelope | Dataset rows/bytes, tables/sources, entity/linkage counts, history depth, update cadence, extraction limits, expected concurrent jobs/releases and approved resource envelope | Data owner + service owner | pending |

**Utility requirement** means the agency's service-performance criterion.
**Operational screening threshold** means a predeclared rule for halting or
progressing the workflow; it is not a privacy guarantee.
**Privacy tolerance/budget** is a distinct justified constraint under a defined
protection claim and mechanism. Attack AUC does not determine epsilon or a
whole-record guarantee.

The public pilot's AUC threshold, sample floors, controls and validity window
are illustrative engineering settings. Do not copy them into S06–S08 as agency
decisions. Scientific work must freeze evaluation data, separate training/
calibration/audit, controls, uncertainty, multiplicity, stopping and selection
rules before final outcomes. Detailed sample sizes and adapter qualification
remain PRD-11/13 deliverables. Public-health scientific review must include
appropriate epidemiological/domain expertise; a technical title alone does not
establish that qualification. Any direct individual-care use needs an identified
clinical safety reviewer before that profile can be accepted.

### Large-data requirements to hand off

- Keep bulk confidential data in the agency data plane. Use versioned snapshots,
  schema/cohort/lineage manifests and scoped query/job access; applications and
  reviewer bundles must not copy complete raw datasets.
- Inventory longitudinal and linked records across programmes, sites, regions
  and time. Define the protected entity and contribution bounds before choosing
  train/calibration/audit partitions or cumulative accounting rules.
- Define how audit cohorts represent the intended population and relevant small
  groups, with approved sampling, uncertainty and exclusion rules. A small local
  fixture or sample cannot establish population-wide performance/privacy.
- Carry forward prior model, statistic, score and component disclosures relevant
  to the recipient's view, even when produced by another programme or ledger.
- Measure training/attack data scans, memory, I/O, worker hours, job concurrency
  and storage retention before promising throughput. Bounded local runners do
  not demonstrate large-dataset support; PRD-07/10/13/21 must evidence it.
- Review model metadata, rare-group outputs, attack traces and reviewer bundles
  as potentially sensitive; a model-only package is not automatically safe.

## Accountable ownership

The four core appointments are required to close PRD-01. Record the named
accountable person or an identifiable, formally assigned office and its delegation
reference. A generic job title without an actual appointment remains pending.
Sensitive identity/contact information can be held in agency-controlled records;
the public-facing repository should retain only approved references.

| Core role | Accountable for | Assignment | Appointment/acceptance evidence |
| --- | --- | --- | --- |
| Service owner | Purpose, scope, utility requirement, resources and delivery responsibility | unassigned | pending |
| Data owner/steward | Data authority, classification, intended population, access, recipient conditions and retention | unassigned | pending |
| Security owner | Threat scope, control requirements, incident ownership and independent security review | unassigned | pending |
| Statistical/scientific owner | Protection claim, mechanism feasibility, epidemiological/domain evaluation, uncertainty and interpretation | unassigned | pending |

S10 must also identify the sponsor and the authority that will appoint policy
and release approvers. Policy authority approves thresholds and exclusions before
execution; release authority later decides an exact eligible release. Those
roles are not supplied by a test pass or by the development assistant.

Declare actual role combinations and conflicts. The submitter/test operator
cannot approve their own release or weaken a policy after seeing results.
Independent assessment must remain independent of the candidate submitter.
Formal identity enrollment and technical role enforcement belong to PRD-06/17;
recording a name here does not implement either service.

## Review record

| Review | Required record | Current state |
| --- | --- | --- |
| Service scope | Owner, date, S01/S02/S04/S06/S09/S11 disposition and exact record revision | not recorded |
| Data scope | Owner, date, S03/S04/S05/S11 and any classification/access conditions | not recorded |
| Security scope | Owner, date, S08/S09, required controls and residual issues | not recorded |
| Scientific scope | Owner, date, S02/S05/S06/S07/S08, claim limits and deferred feasibility work | not recorded |
| Sponsor/policy delegation | Agency authority, owner appointments, policy delegation and conflict resolution | not recorded |

Changes create a new record revision with affected decisions and approvals
identified. Do not backdate approvals or treat the absence of an objection as
agreement. Later scope/policy changes require the applicable fresh evidence and
review, rather than silently rewriting a previously accepted record.

## Completion criteria and handoff

PRD-01 becomes `done` only when:

- S01–S11 have accountable decisions; any `not_applicable` choice has an approved
  reason consistent with the first profile.
- The four core owners are appointed, accept their remit, and role conflicts
  and the policy/release delegation route are recorded.
- The purpose, data/protection scope, candidate, recipient, utility and privacy/
  screening criteria are agreed; unresolved tolerances are not labelled passes.
- Exclusions, prior-disclosure obligations and reassessment triggers are explicit.
- Deferred feasibility and technical work have owners and acceptance criteria,
  with PRD-11/13 responsible for scientific qualification and registration.
- The reviews identify the exact revision and state that scope agreement permits
  public/synthetic assessment staging only. Production data intake and delivery
  still require the later gates.

Current result: **drafting complete; scope agreement incomplete**. The confirmed
direction is agency private cloud and a sector-neutral framework, with a major
public-health agency holding large private data retained as one example pilot. The earlier hospital-operations choice was superseded by the user's
clarification. S01–S11 retain unresolved details and owner appointments are
pending. The question requesting the four accountable owners remains open.

[PRD-02](production-prd02-threat-model.md) now uses this as a preliminary input;
its provider-neutral threat model is drafted with provider and region explicitly
left open by the user. It cannot treat unresolved agency decisions as approved. PRD-03/04 are independent baseline/CI tasks in the parent
plan. This task does not mark them complete or start cloud deployment.

## Evidence and storage boundary

The draft uses existing repository documentation/code and the user's recorded
scope decisions; no agency data,
credentials, infrastructure or production tolerance was inferred. No model or
runtime code was changed for PRD-01. Keep future raw agency inputs and restricted
appointment evidence in approved private custody, outside tracked public
documentation. Local working material, when needed, remains on D:; it is not a
substitute for the production evidence store.
