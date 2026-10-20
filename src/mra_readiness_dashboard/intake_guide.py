"""Static explanations of the fixed draft intake contract, never submitted values.

This presentation catalogue performs no input validation and reads no files.
Its field identifiers are copied from the captured template/report contract.
"""
import re

COMMON_FIELDS = (('decision',
  'Draft scope decision',
  'Describe the proposed decision for this scope item and the reasons a reviewer should examine. The '
  'scope status remains pending; entering text does not record agency agreement.'),
 ('accountable_role',
  'Accountable role',
  'Identify the role proposed to answer for this scope item and explain its remit. This is ordinary '
  'draft text, not an attachment-enforced identifier or an appointment.'),
 ('exact_revision_reference',
  'Exact revision reference',
  'Identify the exact document or scope revision to which the draft decision refers so a reviewer can '
  'distinguish it from later versions. This field is ordinary draft text; the checker does not require '
  'its value to be an attachment identifier.'),
 ('evidence_references',
  'Declared evidence references',
  'List unique attachment identifiers that are present in the separately pinned attachment manifest, '
  "rather than names, paths or URLs. A requirement's primary evidence identifier also belongs in its "
  "parent gap's evidence_references list."),
 ('revision',
  'Separate response revision',
  'Give the response a nonempty revision distinct from uncompleted-template-20261019 while retaining '
  "the template's structure and instructions. This is the response-level revision checked across rows, "
  'not a new revision property to add to each row.'),
 ('appointed_person',
  'Draft appointment identity',
  'Record only a permitted draft identity or identity reference for the relevant core appointment and '
  'keep restricted identities out of the local package. This metadata does not appoint the person or '
  'change the pending appointment status.'),
 ('appointment_reference',
  'Appointment evidence identifier',
  "Use the identifier of a declared attachment containing the appointment evidence, not a person's "
  'name, document path or URL. Presence of the attachment does not authenticate an appointment.'),
 ('accepted_remit_reference',
  'Accepted remit evidence identifier',
  'Use the identifier of a declared attachment recording the remit proposed for review. The reference '
  'must resolve in the attachment manifest; it does not establish that the remit has been accepted by '
  'an authorized agency official.'),
 ('conflict_declaration_reference',
  'Conflict declaration evidence identifier',
  'Use the identifier of a declared attachment containing the relevant conflict declaration. A '
  'resolved identifier alone does not establish that conflicts have been assessed or managed.'),
 ('evidence_reference',
  'Primary evidence identifier',
  'Use the identifier of the declared attachment that supports this requirement and include that same '
  "identifier in the parent gap's evidence_references list. Names, paths and URLs do not substitute "
  'for a declared attachment identifier.'),
 ('evidence_sha256',
  'Primary evidence byte identity',
  'Provide the exact lowercase sixty-four-character hexadecimal SHA-256 recorded for the attachment '
  'named by evidence_reference. A matching hash binds bytes; it does not establish source truth or '
  'agency authority.'),
 ('custodian_reference',
  'Custodian evidence identifier',
  'Use the identifier of a declared attachment supporting the custody record, rather than a '
  "custodian's name or a file location. This identifier must resolve in the attachment manifest but is "
  'not required to appear in the parent gap list merely because it is the custodian reference.'),
 ('configuration_or_scope_revision',
  'Configuration or scope revision',
  "Describe the configuration or scope revision to which this requirement's evidence applies, "
  'including how the reader can distinguish a changed revision. This is ordinary draft text, not an '
  'attachment-enforced identifier.'),
 ('observed_at',
  'Observation instant',
  'Record the observation in the full YYYY-MM-DDTHH:MM:SS form, optionally with one to six fractional '
  'second digits, followed by Z or an explicit +HH:MM or -HH:MM timezone offset. It must not be in the '
  'future relative to the intake checking instant; the checker does not authenticate when the '
  'observation actually occurred.'),
 ('independent_verification',
  'Independent review evidence identifier',
  "Use the identifier of a declared attachment describing the review evidence, not a reviewer's name, "
  'path or URL. It must resolve in the attachment manifest, but need not appear in the parent gap list '
  'merely because it is the review reference; independence and adequacy remain unverified.'),
 ('disposition',
  'Draft disposition',
  'When supplied, this field must be exactly draft. It cannot be used to record accepted evidence, a '
  'closed gap, agency approval or release authority.'),
 ('gap_evidence_references',
  'Parent gap evidence references',
  "This synthetic missing-field code points to the parent gap's existing evidence_references list: "
  "include the same attachment identifier named by the requirement's evidence_reference, not its "
  'Gxx-Exx requirement identifier. Do not add a new gap_evidence_references property or impose this '
  'parent-list requirement on custodian or review identifiers.'))

SCOPE_GROUPS = (('S01',
  'Agency and purpose',
  (('requested_fields.agency_reference',
    'Agency reference',
    'Describe the agency context proposed for the work and a permitted reference that distinguishes it '
    'from other organizations. This requested field is draft scope text and does not establish '
    'sponsorship or authority.'),
   ('requested_fields.jurisdiction',
    'Jurisdiction',
    'Identify the jurisdictions relevant to the proposed activity and why their application needs '
    'review. A named jurisdiction does not settle the legal analysis.'),
   ('requested_fields.programme',
    'Programme',
    'Describe the programme or service in which the proposed use would sit, including the boundary '
    'between this work and adjacent activities. This helps reviewers decide whose remit is relevant.'),
   ('requested_fields.task',
    'Task',
    'Explain the specific task the candidate would support and the decision or workflow it would '
    'affect. Avoid treating a broad model capability as a defined operational task.'),
   ('requested_fields.intended_users_and_decision',
    'Intended users and decision',
    'Describe who would use the outputs and which decisions those users could influence. Include the '
    'distinction between an output being viewed and it being relied on.'),
   ('requested_fields.harmful_errors',
    'Harmful errors',
    'Explain the kinds of mistakes that could harm people or the service and who might bear their '
    'effects. Listing error types is preparation for review, not acceptance of their severity.'),
   ('requested_fields.human_review',
    'Human review',
    'Describe the proposed human review points, the information available to reviewers and their '
    'ability to question or stop reliance. A human being present in a workflow does not by itself '
    'establish effective oversight.'),
   ('requested_fields.benefit_rationale',
    'Benefit rationale',
    'Explain why the proposed use might improve the task and what evidence would be needed to support '
    'that belief. Keep claimed benefits distinct from demonstrated operational usefulness.'))),
 ('S02',
  'Candidate and package',
  (('requested_fields.model_family',
    'Model family',
    "Identify the candidate's general model family and the reason that distinction matters to review. "
    'Naming a family does not select an approved candidate.'),
   ('requested_fields.model_version',
    'Model version',
    'Identify the exact proposed candidate version and how it can be distinguished from later or '
    "related versions. This scopes the draft; it does not verify the package's identity."),
   ('requested_fields.preprocessing',
    'Preprocessing',
    "Describe the transformations and preparation that would shape the candidate's inputs or outputs "
    'and why they affect interpretation. A summary does not validate those transformations.'),
   ('requested_fields.source_and_dependency_provenance',
    'Source and dependency provenance',
    'Describe where candidate components and dependencies come from and the records a reviewer would '
    'need to trace them. Separate a claimed origin from verified provenance.'),
   ('requested_fields.parent_and_component_lineage',
    'Parent and component lineage',
    "Explain the candidate's relationship to parent models, adapted components or other contributing "
    'packages. Include lineage changes that could alter which evidence remains relevant.'))),
 ('S03',
  'Data and classification',
  (('requested_fields.dataset_and_snapshot_references',
    'Dataset and snapshot references',
    'Identify the proposed datasets and the particular snapshots relevant to the draft scope. '
    'Distinguish a named source from an exact historical data state without admitting new source bytes '
    'here.'),
   ('requested_fields.population',
    'Population',
    'Describe the population the proposed data represent and the population the intended decision '
    'would concern. Explain material differences rather than assuming coverage transfers between '
    'them.'),
   ('requested_fields.source_authority',
    'Source authority',
    "Explain the proposed source's standing and what evidence would support lawful and appropriate "
    'use. An official-looking source label does not establish reuse permission or fitness for this '
    'task.'),
   ('requested_fields.classification',
    'Classification',
    'Describe the data classification proposed for review and the reasons sensitive or restricted '
    'treatment may apply. The entry does not assign an accepted classification.'),
   ('requested_fields.residency',
    'Residency',
    'Identify the places where data or outputs are expected to reside and any unresolved location '
    'constraints. Distinguish an intended location from an accepted hosting arrangement.'),
   ('requested_fields.retention',
    'Retention',
    'Describe the proposed retention purposes, periods and obligations that reviewers would need to '
    'reconcile. Do not treat this draft as an approved retention schedule.'),
   ('requested_fields.repeated_records',
    'Repeated records',
    'Explain how the same person or entity may recur within the proposed data and why that matters to '
    'review. Repeated appearances can affect the interpretation of both evidence and protection '
    'claims.'),
   ('requested_fields.cross_source_linkage',
    'Cross-source linkage',
    'Describe proposed or existing links between sources and the additional relationships those links '
    "could reveal. Review the combined context rather than assuming each source's separate treatment "
    'is sufficient.'),
   ('requested_fields.cohort_conditions',
    'Cohort conditions',
    'Explain how records or people would enter, remain in or leave the proposed cohort. These '
    'boundaries help reviewers identify exclusions and changes in who is represented.'),
   ('requested_fields.sensitive_or_protected_fields_schema_reference',
    'Sensitive or protected fields schema reference',
    'Describe a permitted schema reference that identifies sensitive or protected field categories '
    'without copying protected values into the local draft. This requested scope field is ordinary '
    'text, not an attachment-enforced identifier.'))),
 ('S04',
  'Recipient and disclosure',
  (('requested_fields.recipient_reference',
    'Recipient reference',
    'Identify the proposed recipient context and distinguish it from other users or onward recipients. '
    'Naming a recipient does not authorize disclosure to that recipient.'),
   ('requested_fields.purpose',
    'Disclosure purpose',
    'Explain the purpose for which the proposed recipient would receive or use the material. Review '
    'whether that purpose differs from the purpose for which the data were originally obtained.'),
   ('requested_fields.interface',
    'Recipient interface',
    'Describe the proposed way a recipient would access outputs and the kinds of material exposed '
    'through it. Interface descriptions scope review without enabling a delivery route.'),
   ('requested_fields.retained_copies_and_outputs',
    'Retained copies and outputs',
    'Describe what copies or outputs a recipient could retain and the obligations those retained '
    'materials might create. A local presentation change cannot retract material already held '
    'elsewhere.'),
   ('requested_fields.onward_use',
    'Onward use',
    'Explain proposed onward uses, transfers or combinations with other material, together with '
    "unresolved limits. Do not assume the first recipient's proposed purpose covers every later use."),
   ('requested_fields.prior_disclosure_history_reference',
    'Prior disclosure history reference',
    'Describe a permitted reference to earlier disclosures relevant to the proposed recipient and '
    'purpose, including any gaps in that history. This is draft text and does not reconstruct '
    'authoritative cumulative history.'))),
 ('S05',
  'Protection claim',
  (('requested_fields.protected_unit',
    'Protected unit',
    'Explain what person, entity or other unit the proposed protection claim is intended to concern. '
    'Keep that claim distinct from the physical layout of the data records.'),
   ('requested_fields.adjacency',
    'Neighboring data assumption',
    'Describe in words the change in the underlying data that the proposed protection claim is meant '
    'to cover. This records an assumption for review without asserting that a mechanism satisfies it.'),
   ('requested_fields.raw_to_derived_contribution_map',
    'Raw to derived contribution map',
    "Explain how a protected unit's raw records could contribute to derived material or outputs. "
    'Reviewers need this relationship to understand what a proposed protection claim actually covers.'),
   ('requested_fields.public_feature_status',
    'Public feature status',
    'Describe which proposed features are claimed to be public and the evidence needed to justify that '
    'status. Public availability does not by itself settle reuse terms or protection consequences.'),
   ('requested_fields.membership_and_attribute_scope',
    'Membership and attribute scope',
    'Explain whether the claim concerns the presence of a unit, information about its attributes or '
    'both, and where the claim stops. Avoid treating these different disclosure questions as '
    'interchangeable.'),
   ('requested_fields.mechanism_and_composition_assumptions',
    'Mechanism and composition assumptions',
    'Describe the assumptions behind the proposed protection method and how repeated or combined '
    'disclosures are expected to be considered. This field does not establish a valid privacy '
    'guarantee or an accepted cumulative limit.'))),
 ('S06',
  'Utility and impact',
  (('requested_fields.decision_horizon_and_origin',
    'Decision horizon and origin',
    'Describe when a decision would be made and which future period it is intended to concern. The '
    'timing determines what information a realistic decision maker could have had.'),
   ('requested_fields.target_and_unit',
    'Target and unit',
    'Explain the outcome of interest and the unit in which it would be interpreted by the intended '
    'user. Keep the target consistent with the task rather than substituting a convenient available '
    'measure.'),
   ('requested_fields.metric_and_direction',
    'Evaluation measure and direction',
    'Describe the proposed evaluation measure and what improvement would mean in that measure. The '
    'draft does not select an accepted measure or validate its connection to operational benefit.'),
   ('requested_fields.positive_practical_margin',
    'Practical benefit margin rationale',
    'Explain how a worthwhile benefit margin would need to be justified prospectively for the intended '
    'decision, without selecting a threshold here. The top-level agency_practical_margin remains null '
    'and this text does not accept scientific criteria.'),
   ('requested_fields.benefit_and_cost_rationale',
    'Benefit and cost rationale',
    'Describe the factors a reviewer should consider when weighing expected benefit, operational cost '
    'and potential harm. Separate a reasoned proposal from an agency-approved trade-off.'),
   ('requested_fields.credible_alternatives_and_information',
    'Credible alternatives and information',
    'Identify realistic alternatives and the information each could legitimately use at the decision '
    'time. A comparison is not credible merely because an alternative is easy to outperform.'),
   ('requested_fields.harmful_error_limits',
    'Harmful error limits',
    'Explain which harmful error limits would need an accountable prospective decision and the '
    'affected interests behind them. Do not choose or imply an accepted tolerance in this draft '
    'guide.'),
   ('requested_fields.affected_group_criteria',
    'Affected group criteria',
    'Describe the groups whose outcomes warrant separate consideration and the reasons their effects '
    'may differ. Any criteria for acceptable effects still require an attributable decision.'),
   ('requested_fields.uncertainty_and_selection_rules',
    'Uncertainty and selection rules',
    'Explain how uncertainty and the selection of candidates or reported results should be considered '
    'before evaluation. This is a request for a reviewable plan, not a new scientific test or an '
    'accepted result.'))),
 ('S07',
  'Privacy constraint',
  (('requested_fields.justified_tolerance_or_cumulative_budget',
    'Tolerance or cumulative budget rationale',
    'Explain the factors that would justify a proposed tolerance or cumulative disclosure limit for '
    'the protected context. Do not choose a limit or imply that this draft grants protected-data '
    'authority.'),
   ('requested_fields.protected_scope_reference',
    'Protected scope reference',
    'Describe a permitted reference to the exact protected scope to which the proposed constraint '
    'would apply. This requested scope field is ordinary draft text, not an attachment-enforced '
    'identifier.'),
   ('requested_fields.prior_spending_and_disclosure',
    'Prior spending and disclosure',
    'Describe the earlier disclosures or use of protection allowances that must be considered and any '
    'uncertainty about them. A partial history must not be represented as an authoritative complete '
    'account.'),
   ('requested_fields.accountant_and_assumptions',
    'Accounting approach and assumptions',
    'Explain the proposed approach to accounting for combined disclosures and the assumptions on which '
    'it depends. Naming an approach does not validate its suitability or establish a recoverable '
    'current account.'),
   ('requested_fields.unknown_history_treatment',
    'Unknown history treatment',
    'Explain how missing or uncertain disclosure history would be handled and which decisions remain '
    'blocked by it. Do not turn an absence of records into an assumption that no earlier disclosure '
    'occurred.'))),
 ('S08',
  'Required screens and independent review',
  (('requested_fields.recipient_realistic_threats',
    'Recipient-realistic threats',
    'Describe plausible threats in the intended recipient context, including information or access the '
    'recipient may already have. Threats should be grounded in that context rather than an abstract '
    'capability label.'),
   ('requested_fields.required_attacks_and_interfaces',
    'Required screens and interfaces',
    'Explain which challenge or attack screens and exposed interfaces the proposed review would need '
    'to consider. Describing them does not execute a screen or establish that the candidate has passed '
    'one.'),
   ('requested_fields.controls',
    'Proposed controls',
    'Describe the proposed controls and the specific risks each is intended to address, including '
    'unresolved dependencies. A listed control is not evidence that it is deployed or effective.'),
   ('requested_fields.stopping_and_blocking_rules',
    'Stopping and blocking rules',
    'Explain the conditions that should stop a review, prevent reliance or block progression, and who '
    'would need authority to apply them. This draft does not create those operational powers.'),
   ('requested_fields.permitted_exclusions',
    'Permitted review exclusions',
    'Describe any proposed exclusions from screening or review and why an accountable reviewer would '
    'need to consider them. Do not treat an omitted screen as already accepted.'),
   ('requested_fields.independent_review_qualification',
    'Independent review qualification',
    'Explain the expertise, independence and conflict conditions needed for the intended reviewer. A '
    'qualification description does not appoint or authenticate an independent reviewer.'))),
 ('S09',
  'Scope limits and reassessment',
  (('requested_fields.accepted_exclusions',
    'Scope exclusions for review',
    'Describe the exclusions whose exact scope and acceptance evidence would need to be reviewed. The '
    'field name does not mean exclusions have been accepted by the agency.'),
   ('requested_fields.unresolved_issues',
    'Unresolved issues',
    'List the unresolved questions that could affect reliance and explain their consequences for the '
    'proposed scope. Keep uncertainty visible instead of converting it into a completion claim.'),
   ('requested_fields.package_data_interface_recipient_change_triggers',
    'Package, data, interface and recipient changes',
    'Explain which changes to the candidate package, data, interface or recipient should trigger '
    'reassessment and why. Evidence that applied to an earlier configuration may not cover the changed '
    'one.'),
   ('requested_fields.new_disclosure_or_invalid_evidence_triggers',
    'New disclosure or invalid evidence triggers',
    'Describe how a new disclosure or discovery of invalid evidence should lead to reassessment of '
    'prior reliance. The proposed trigger does not itself repair evidence or recover authority.'),
   ('requested_fields.maintenance_and_retirement_requirements',
    'Maintenance and retirement requirements',
    'Explain the responsibilities and evidence needed to maintain, withdraw or retire the proposed '
    'use. Include obligations that may continue after active use ends.'),
   ('requested_fields.policy_change_triggers',
    'Policy change triggers',
    'Describe policy or regulatory changes that should prompt a new scope or authority review. This '
    'field does not determine which change has legally occurred or approve a response to it.'))),
 ('S10',
  'Decision authority',
  (('requested_fields.sponsor_reference',
    'Sponsor reference',
    'Describe the proposed sponsor context and a permitted reference needed for an accountable '
    'sponsorship review. This requested field is draft text and does not establish sponsorship or '
    'delegated authority.'),
   ('requested_fields.core_owner_appointments',
    'Core owner appointments',
    'Describe the appointment evidence and remits that the four core ownership roles would need. The '
    'separate appointment rows remain pending; a summary here does not appoint anyone.'),
   ('requested_fields.policy_delegation',
    'Policy delegation',
    'Explain the policy decision powers proposed for delegation and the evidence needed to establish '
    'their limits. Keep a proposed delegation distinct from an authorized current delegation.'),
   ('requested_fields.release_delegation',
    'Release delegation',
    'Describe who would need authority for a release decision and the boundaries of any proposed '
    'delegation. Entering this text cannot authorize a pilot, release or disclosure.'),
   ('requested_fields.role_combinations_and_conflicts',
    'Role combinations and conflicts',
    'Explain any proposed combination of roles and the conflicts or loss of independence that '
    'combination could create. Reviewers need a reasoned account rather than an assumption that one '
    'person can accept every role.'),
   ('requested_fields.independent_reviewer_appointments',
    'Independent reviewer appointments',
    'Describe the appointments and remit evidence needed for independent review, including the '
    'separation from accountable delivery roles. No reviewer is appointed by the draft or the field '
    'guide.'))),
 ('S11',
  'Scale and operating envelope',
  (('requested_fields.dataset_rows_and_bytes',
    'Dataset size',
    'Describe the proposed data volume and the records on which that estimate depends. A draft '
    'estimate does not establish accepted capacity or a measured production workload.'),
   ('requested_fields.tables_and_sources',
    'Tables and sources',
    'Identify the tables and sources expected within the operating scope and why their structure '
    'matters to review. A source being listed does not admit it for use.'),
   ('requested_fields.entity_and_linkage_counts',
    'Entities and linkage scale',
    'Describe the expected scale of distinct entities and their links, including uncertainty in those '
    'estimates. This helps distinguish record volume from the relationships an operating service would '
    'handle.'),
   ('requested_fields.history_depth',
    'History depth',
    'Explain how much historical material the proposed use needs and why that history is relevant. '
    'Separate required history from history that has actually been captured and qualified.'),
   ('requested_fields.update_cadence',
    'Update cadence',
    'Describe how often relevant inputs or outputs are expected to change and what decisions depend on '
    'that timing. A proposed cadence is not an availability or freshness commitment.'),
   ('requested_fields.extraction_limits',
    'Extraction limits',
    'Explain the proposed limits and conditions on obtaining material from each source, including '
    'unresolved permissions. This draft does not authorize extraction or run a retrieval.'),
   ('requested_fields.concurrent_jobs_and_releases',
    'Concurrent work and releases',
    'Describe the anticipated overlap of jobs or release requests and why it matters to the intended '
    'service. No concurrency capacity or release authority is established by the estimate.'),
   ('requested_fields.resource_and_cost_envelope',
    'Resources and costs',
    'Explain the resources, costs and constraints that accountable owners would need to review for the '
    'proposed workload. Do not present an unaccepted estimate as a funded or qualified operating '
    'envelope.'),
   ('requested_fields.service_and_recovery_objectives',
    'Service and recovery objectives',
    'Describe proposed service and recovery objectives and the decisions or evidence needed to justify '
    'them. Local presentation checks do not accept an availability target or demonstrate production '
    'recovery.'))))

FIELD_ENTRIES = COMMON_FIELDS + tuple(entry for _, _, fields in SCOPE_GROUPS for entry in fields)
FIELD_CODES = tuple(code for code, _, _ in FIELD_ENTRIES)
FIELD_ANCHORS = {code: "field-" + re.sub(r"[^a-z0-9]+", "-", code).strip("-") for code in FIELD_CODES}
assert len(FIELD_CODES) == 93 and len(set(FIELD_CODES)) == 93
assert len(set(FIELD_ANCHORS.values())) == 93
assert all(re.fullmatch(r"field-[a-z0-9]+(?:-[a-z0-9]+)*", anchor) for anchor in FIELD_ANCHORS.values())
