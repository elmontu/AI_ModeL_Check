"""Fixed fictional lessons, separate from operational intake and real authority.

No files, network, service controls or scientific work are accessed by this module.
Selection returns fresh validated teaching objects; all real decisions stay pending.
"""
from copy import deepcopy
import json

SCENARIO_IDS = ("starting-point", "draft-decisions", "reviewed-decisions", "traceable-sources", "worked-example")
SCENARIO_OPTIONS = (("starting-point", "Starting point"), ("draft-decisions", "Draft decisions"), ("reviewed-decisions", "Reviewed fictional decisions; sources unresolved"), ("traceable-sources", "Traceable synthetic sources"), ("worked-example", "Complete worked fictional example"))
DEFAULT_SCENARIO_ID = "starting-point"

_DECISION_FACTORS = (('S01 - Agency and purpose',
  'A useful scope links a defined decision to affected users and accountable responsibility.',
  'An attributable real agency, jurisdiction, programme, task, user, harm and human-review '
  'decision.',
  ('The fictional Service Planning Office has no selected purpose for toy-planning-package-A; the '
   'Planning Circle use and exclusions are unanswered.',
   'The fictional Service Planning Office proposes human discussion of invented information-desk '
   'categories for its Information Desk Capacity Review. Individual eligibility, ranking and '
   'automated decisions are excluded.',
   'In the fictional review note for teaching-revision-A, the Service Planning Office purpose is '
   'human discussion of invented information-desk categories by the Planning Circle. Individual '
   'eligibility, ranking and automated decisions are outside scope.',
   'The fictional Service Planning Office retains the same discussion-only Information Desk '
   'Capacity Review for the Planning Circle; synthetic source traceability changes evidence '
   'maturity, not the purpose or exclusions.',
   'The worked fictional Service Planning Office record fixes the Information Desk Capacity Review '
   'as human discussion of invented desk categories by the Planning Circle, with no individual '
   'eligibility, ranking or automated decisions.')),
 ('S02 - Candidate and package',
  'Evidence belongs to an exact package and scope; a change can invalidate earlier review.',
  'An exact real candidate identity, provenance, component lineage and applicable scope review.',
  ('The name toy-planning-package-A is a teaching label only; no package description or exact '
   'lesson revision is selected.',
   'The proposed toy-planning-package-A is a read-only planning note and category dictionary at '
   'teaching-revision-A. It contains no executable candidate, fitted model or performance result.',
   'The fictional Review Circle note is bound to toy-planning-package-A at teaching-revision-A: a '
   'read-only planning note and category dictionary, with no executable candidate or performance '
   'claim.',
   'The package remains toy-planning-package-A at teaching-revision-A. The separate source issues '
   'toy-first-issue and toy-correction-issue do not silently change the package identity.',
   'The worked package record is toy-planning-package-A at teaching-revision-A, comprising a '
   'read-only planning note and category dictionary. No executable model, delivery artifact or '
   'performance outcome is included.')),
 ('S03 - Data and classification',
  'Population, sensitive fields and linked records affect the people and obligations a review must '
  'consider.',
  'Actual dataset and snapshot identities, population, classification, residency, retention and '
  'linkage decisions.',
  ('No population, category dictionary, classification or residence condition is selected for the '
   'fictional office.',
   'The proposed material contains only invented aggregate desk categories: Directions, Form '
   'Guidance and Appointment Information. It contains no people, protected records or person-level '
   'linkage.',
   'The fictional decision record describes only invented aggregate Directions, Form Guidance and '
   'Appointment Information categories. No people, protected records or person-level linkage are '
   'in the teaching scope; source definitions remain unresolved.',
   'The toy-category-dictionary-A defines Directions as wayfinding, Form Guidance as procedural '
   'form help and Appointment Information as booking-process information. All descriptions are '
   'invented, with no people, protected records or linkage.',
   'The worked data record uses only toy-category-dictionary-A and the invented aggregate '
   'Directions, Form Guidance and Appointment Information descriptions. No real observation, '
   'person, protected record, linkage or accepted real classification is supplied.')),
 ('S04 - Recipient and disclosure',
  'Recipients, interfaces and retained copies can change the consequences of sharing the same '
  'material.',
  'An attributable real recipient, purpose, interface, retention, onward-use and prior-disclosure '
  'decision.',
  ('The fictional Planning Circle is only a possible recipient; no interface, use, retention or '
   'onward-sharing condition is selected.',
   'The proposed recipient is the fictional Planning Circle, an internal teaching group reading a '
   'static planning note. Its proposed use is discussion only, with no onward sharing or '
   'individual decisions.',
   'The fictional review note fixes the Planning Circle as the internal teaching recipient for '
   'read-only discussion, with no onward sharing or individual decisions. Its teaching-note '
   'retention condition grants no real access or deletion authority.',
   'The same Planning Circle reads the static teaching note for discussion only, with no onward '
   'sharing or individual decisions. The invented source terms are checked separately from these '
   'recipient conditions.',
   'The worked recipient record names only the fictional Planning Circle, with read-only teaching '
   'access, discussion-only use and no onward sharing or individual decisions. A lesson-only '
   'retention condition does not alter or delete actual evidence.')),
 ('S05 - Protection claim',
  'A claim needs a defined unit, contributions and exclusions; a mechanism name cannot supply '
  'them.',
  'Accountable protected-unit, contribution, membership, attribute and mechanism-scope decisions.',
  ('No protected unit, contribution boundary or privacy guarantee is selected.',
   'The proposed unit is an invented category-period description, not a person or household. No '
   'membership, attribute or protected-data privacy guarantee is claimed.',
   'The fictional review records the invented category-period description as the teaching unit and '
   'excludes person, household, membership and attribute guarantees. No protected-data mechanism '
   'or authority is accepted.',
   'The synthetic source ledger describes category-period material only; it establishes neither a '
   'privacy guarantee nor authentic public availability. No protected-data mechanism is selected.',
   'The worked protection record states that only invented category-period descriptions are used '
   'and no person, household, membership or attribute guarantee is made. The lesson contains no '
   'protected-data authority or claimed privacy mechanism.')),
 ('S06 - Utility and impact',
  'Worthwhile benefit and harmful-error limits need prospective reasons tied to actual decisions.',
  'Approved prospective criteria, practical benefit and harm rationale, alternatives and '
  'independent exact-revision review.',
  ('No benefit rule, harm tolerance or alternative is selected for the fictional review.',
   'The proposed benefit is clearer human discussion of desk-category meaning. The named harms are '
   'definition confusion and overreliance in staffing discussion; current manual notes and no '
   'package are alternatives. No threshold or measured benefit is chosen.',
   'The fictional Review Circle records a qualitative rationale for discussion only: compare the '
   'package with current manual notes and no package, and pause on definition mismatch or missing '
   'traceability. No numerical rule, measured benefit or scientific acceptance is present.',
   'The same qualitative discussion rationale remains in place; the synthetic ledger can clarify '
   'traceability but cannot demonstrate benefit, tolerable harm or superiority to current manual '
   'notes or no package.',
   'The worked rationale names clearer category discussion as the hoped-for benefit, definition '
   'confusion and overreliance as harms, and current manual notes or no package as alternatives. '
   'Use remains human discussion only, with a pause for definition mismatch or missing lineage; no '
   'measured benefit or scientific success is asserted.')),
 ('S07 - Privacy constraint',
  'Repeated disclosures and incomplete history can change a proposed constraint.',
  'A justified real constraint, protected scope, authoritative prior-disclosure account and policy '
  'decision.',
  ('No privacy allowance, protected scope or prior-disclosure account is selected.',
   'The draft permits only invented teaching descriptions and proposes no privacy allowance or '
   'protected-data use. Unknown disclosure history blocks any extension beyond that synthetic '
   'scope.',
   'The fictional review condition is synthetic-only discussion with no protected-data permission '
   'or allowance. Unknown prior history is not treated as unused allowance and blocks outside '
   'reuse.',
   'The synthetic source ledger is not a disclosure-history account. The fictional condition '
   'remains synthetic-only discussion, with no privacy allowance or protected-data permission and '
   'no outside reuse on unknown history.',
   'The worked privacy record contains no allowance or protected-data permission. It limits the '
   'lesson to invented descriptions and treats unknown prior disclosure history as a reason to '
   'stop any proposed extension, not as unused capacity.')),
 ('S08 - Screens and independent review',
  'Screens need a realistic remit, qualified reviewers and separation from delivery interests.',
  'Actual threat scope, required screens, blocking rules, exclusions, qualifications, conflicts '
  'and exact-revision review.',
  ('No reviewer remit, conflict assessment, screen or review note is selected.',
   'The proposed Review Circle is separate from the Drafting Circle and has no drafting or '
   'delivery role. Its proposed remit is the teaching-revision-A decision and source checklist; '
   'overlap or conflicts require recusal and replacement. No screen is run.',
   'The fictional Review Circle note identifies teaching-revision-A, a '
   'decision-and-source-checklist remit, separation from drafting and delivery, and a '
   'disclosed-overlap rule requiring recusal and replacement. Reviewer competence remains a '
   'fictional assumption; no attack, screen or agency-qualified acceptance occurs.',
   'The same fictional Review Circle examines teaching-revision-A and toy-source-ledger-A within '
   'its decision-and-lineage remit. It has no drafting or delivery role, and overlap requires '
   'recusal and replacement; source authentication and executed screens are outside the note.',
   'The worked review record binds the separate fictional Review Circle to teaching-revision-A and '
   'toy-source-ledger-A, states its checklist remit and assumed competence, discloses overlap and '
   'requires recusal and replacement. It records no executed screen, real appointment or '
   'agency-qualified acceptance.')),
 ('S09 - Limits and reassessment',
  'Changes and unresolved issues need triggers for new review rather than inherited acceptance.',
  'Accepted limits, issue dispositions and package, data, recipient, policy, maintenance and '
  'retirement triggers.',
  ('No reassessment trigger or limit disposition is selected.',
   'The draft discussion stops on a category-definition mismatch, missing lineage, a newly noticed '
   'correction, or a change to the package, purpose or recipient. Unresolved issues remain visible '
   'rather than deferred as accepted.',
   'The fictional review note retains discussion-only use and a pause for definition mismatch, '
   'missing lineage, new corrections or package, purpose and recipient changes. The Review Circle '
   'has no power to accept real deferrals.',
   'The publication of toy-correction-issue after toy-decision-cutoff triggers fictional '
   'reconsideration of the current teaching note, while the earlier toy-first-issue remains '
   'retained. It does not rewrite the earlier cutoff record.',
   'The worked limits record pauses discussion for definition mismatch, absent lineage, correction '
   'or scope change. Toy-correction-issue triggers a new current-view review while toy-first-issue '
   'is retained; ending the lesson does not retire or delete actual project evidence.')),
 ('S10 - Decision authority',
  'A role label, signature-shaped field or local record cannot establish real decision powers.',
  'Authenticated sponsor and owner appointments, accepted remits, delegation limits and conflict '
  'records.',
  ('No real or fictional role appointment is represented; real agency appointments remain pending.',
   'The Service Planning Office draft assigns only fictional role labels within the Drafting '
   'Circle and a separate Review Circle. It supplies no real names, signatures, delegation or '
   'appointment.',
   'The fictional remit record separates Drafting Circle service, data, security and scientific '
   'responsibilities from the Review Circle, which has no drafting, delivery or real delegation '
   'role. All actual appointments and authority remain pending.',
   'The same fictional remit separation applies to toy-planning-package-A and toy-source-ledger-A. '
   'The Review Circle cannot authenticate a real custodian, grant source rights or exercise agency '
   'delegation.',
   'The worked authority record contains only fictional Drafting Circle and Review Circle remits, '
   'no actual names, signatures, appointments or delegation. Real agency decisions remain pending '
   'and authorization effect remains none.')),
 ('S11 - Scale and operating envelope',
  'Operating objectives depend on actual workload, costs and accountable responsibilities.',
  'An accepted real workload and resource envelope, operating ownership, service and recovery '
  'objectives and retirement obligations.',
  ('No workload, operating owner, service objective or recovery commitment is selected.',
   'The draft operating context is a static internal teaching session, not an operational service. '
   'Human review effort and stewardship are considerations; there are no workload measurements, '
   'capacity targets or recovery promises.',
   'The fictional review accepts only the lesson assumption of a static Planning Circle '
   'discussion, with Drafting Circle stewardship of the teaching note. It supplies no measured '
   'workload, availability objective, production acceptance or recovery commitment.',
   'The static discussion context is unchanged when toy-correction-issue appears; the fictional '
   'data remit flags the update for review. No source-update workload, capacity or recovery test '
   'is run.',
   'The worked operating record describes a static internal teaching session with Drafting Circle '
   'stewardship and a pause on changed sources. It contains no production service, measured '
   'capacity, availability promise or recovery commitment; lesson-note retirement has no effect on '
   'retained real evidence.')),
 ('Core role - Service owner',
  'Service accountability joins purpose, practical benefit, resources and conditions for reliance.',
  'A real service-owner appointment, accepted remit, qualifications, conflicts and applicable '
  'delegation.',
  ('The fictional service-owner remit is unassigned.',
   'The Drafting Circle service remit proposes the Information Desk Capacity Review purpose, '
   'discussion-only reliance, Planning Circle recipient conditions and human review effort. It is '
   'a fictional remit, not an appointment.',
   'The fictional reviewed service remit owns the discussion-only purpose, recipient conditions '
   'and pause on scope change for teaching-revision-A. It belongs to the Drafting Circle, separate '
   'from the Review Circle; no real person is appointed.',
   'The same fictional Drafting Circle service remit pauses Planning Circle reliance when '
   'toy-source-ledger-A lacks a definition or timing link. Source traceability does not enlarge '
   'the discussion-only purpose.',
   'The worked service remit belongs to the fictional Drafting Circle: purpose, practical '
   'rationale, human review effort, Planning Circle conditions and change-trigger ownership. It '
   'remains separate from Review Circle review and grants no real appointment or reliance '
   'authority.')),
 ('Core role - Data owner',
  'Data ownership includes provenance, access, classification and appropriate use, not mere file '
  'possession.',
  'A real data-owner appointment and accepted remit with authority, qualification and conflict '
  'evidence.',
  ('The fictional data-owner remit is unassigned.',
   'The Drafting Circle data remit proposes custody of the invented category dictionary, '
   'source-definition questions and lesson-only access boundaries. It grants no ownership or '
   'admission of a real source.',
   'The fictional reviewed data remit covers invented category definitions, proposed provenance '
   'and rights questions at teaching-revision-A. It belongs to the Drafting Circle and cannot turn '
   'unresolved source records into authentic evidence.',
   'The fictional Drafting Circle data remit maintains toy-category-dictionary-A and '
   'toy-source-ledger-A, retains both toy-first-issue and toy-correction-issue, and excludes the '
   'later correction at toy-decision-cutoff. Custody is simulated, not authentic.',
   'The worked data remit belongs to the fictional Drafting Circle and covers the invented '
   'dictionary, teaching-only access terms, issue custody and cutoff lineage. No real source is '
   'owned, admitted, authenticated or made legally reusable.')),
 ('Core role - Security owner',
  'Security responsibility includes realistic threats, blocking and incident ownership as well as '
  'controls.',
  'A real security-owner appointment, accepted remit and conflicts with accountable operational '
  'responsibilities.',
  ('The fictional security-owner remit is unassigned.',
   'The Drafting Circle security remit proposes read-only teaching access for the Planning Circle '
   'and a stop when scope or evidence is uncertain. It does not operate a security service or '
   'qualify infrastructure.',
   'The fictional reviewed security remit covers discussion-only access, no onward sharing, '
   'evidence-change escalation and incident questions for teaching-revision-A. It does not execute '
   'screens or grant operational acceptance.',
   'The fictional Drafting Circle security remit treats a changed or missing toy-source-ledger-A '
   'link as a reason to stop reliance and seek review. A consistent toy ledger does not prove '
   'independent custody or every delivery route.',
   'The worked security remit belongs to the fictional Drafting Circle: read-only teaching scope, '
   'no onward sharing, stop conditions and escalation responsibility. It contains no real security '
   'appointment, executed screen, infrastructure qualification or complete-route assurance.')),
 ('Core role - Scientific owner',
  'Scientific accountability connects the intended claim to eligible evidence and defensible '
  'interpretation.',
  'A real scientific-owner appointment, accepted remit, qualifications, conflicts and '
  'independent-review arrangements.',
  ('The fictional scientific-owner remit is unassigned.',
   'The Drafting Circle scientific remit distinguishes qualitative teaching discussion from a '
   'performance claim and records evidence eligibility questions. It proposes no model, benchmark '
   'or scientific result.',
   'The fictional reviewed scientific remit records that teaching-revision-A makes no empirical '
   'performance claim. The separate Review Circle examines rationale and limitations, with no '
   'accepted real scientific decision or validation result.',
   'The fictional Drafting Circle scientific remit classifies toy-first-issue and '
   'toy-correction-issue as fabricated teaching records, not untouched validation. Traceability '
   'therefore supports no future, population or person-level validity claim.',
   'The worked scientific remit belongs to the fictional Drafting Circle and retains no empirical '
   'performance claim, with Review Circle review of exact-revision rationale and limitations. It '
   'preserves the real adverse and unsupported findings; no model selection, benchmark or '
   'scientific acceptance occurs.')))

_SOURCE_FACTORS = (('Provenance and custody',
  'A traceable path and byte identity do not prove the original issuer or independent control.',
  'Authentic source provenance, byte identities, accountable custodianship and independent custody '
  'evidence where required.',
  ('The possible toy-source-set-A is a label only; no issuer, custodian or lineage record is '
   'selected.',
   'The proposed toy-source-set-A contains invented desk-category descriptions for '
   'toy-planning-package-A. Its issuing and custody records are not yet supplied, so provenance '
   'remains unresolved.',
   'The same toy-source-set-A remains unresolved: the fictional decision review at '
   'teaching-revision-A supplies no first-issue record, authenticated issuer or custody evidence.',
   'The invented toy-source-ledger-A names the fictional Service Planning Office as toy issuer and '
   'the Drafting Circle data remit as toy custodian. Its links join fabricated issues only; no '
   'real issuer or independent custody is authenticated.',
   'The worked toy-source-ledger-A links the fictional Service Planning Office toy issuer, '
   'Drafting Circle data custodian, toy-first-issue and toy-correction-issue. These are internally '
   'consistent invented records, not authentic source provenance or independent custody.')),
 ('Definitions and comparability',
  'Similar labels need not describe the same units, populations or reporting regimes.',
  'Source-bound definitions, units, measurement ownership, reporting regimes and independent '
  'comparability review.',
  ('No definition is selected for Directions, Form Guidance or Appointment Information.',
   'The draft dictionary proposes Directions for wayfinding, Form Guidance for procedural form '
   'help and Appointment Information for booking-process information. The broader candidate label '
   'Guidance is unresolved and is not merged with those categories.',
   'The fictional purpose review retains Directions, Form Guidance and Appointment Information, '
   'but the candidate label Guidance has no source-bound definition. The lesson therefore leaves '
   'source comparability unresolved.',
   'The invented toy-category-dictionary-A defines Directions as wayfinding, Form Guidance as '
   'procedural form help and Appointment Information as booking-process information. The ambiguous '
   'label Guidance stays separate rather than being silently equated.',
   'The worked toy-category-dictionary-A retains the same Directions, Form Guidance and '
   'Appointment Information meanings and keeps ambiguous Guidance separate. Definitions apply to '
   'invented category descriptions only; no actual series comparability is accepted.')),
 ('Artifact-specific reuse conditions',
  "Another dataset's licence or public availability cannot supply permission for this exact "
  'artifact and use.',
  'Applicable artifact-and-use-specific terms, attribution, restrictions and attributable '
  'permission or admission decisions.',
  ('No artifact-specific reuse condition is selected or assumed.',
   'The draft asks whether toy-source-set-A may be used in the fictional Planning Circle '
   'discussion. No terms record or real permission is supplied.',
   'Artifact-specific rights for toy-source-set-A remain unresolved even though the fictional '
   'Review Circle has examined the purpose. Decision review grants no source permission.',
   'The invented toy-teaching-terms-A applies only to toy-category-dictionary-A and fabricated '
   'issue descriptions for read-only Planning Circle teaching discussion, with no onward sharing. '
   'It grants no real legal permission.',
   'The worked rights record is the invented toy-teaching-terms-A, limited to the same fabricated '
   'dictionary and issue descriptions, Planning Circle teaching purpose and no onward sharing. No '
   'actual artifact rights or admission decision is represented.')),
 ('Original vintages',
  'Current values do not prove which values were available at an earlier decision origin.',
  'Authentic original bytes and identities matched to every proposed value, dependency and origin.',
  ('No original issue or decision cutoff is selected.',
   'The proposed labels toy-first-issue, toy-correction-issue and toy-decision-cutoff have no '
   'release evidence yet; current descriptions are not treated as earlier originals.',
   'The source labels toy-first-issue and toy-correction-issue still lack a supported ordering '
   'around toy-decision-cutoff. The fictional decision review does not establish original '
   'availability.',
   'In the invented ledger, toy-first-issue is first published before toy-decision-cutoff and is '
   'eligible only under that lesson assumption. Toy-correction-issue is published after the cutoff '
   'and excluded at that earlier origin.',
   'The worked invented ledger places toy-first-issue before toy-decision-cutoff and uses it only '
   'under the fictional eligibility assumption. Toy-correction-issue is published after the '
   'cutoff, excluded there, and never backfilled as the earlier original; no authentic vintage is '
   'supplied.')),
 ('Release evidence and precision',
  'A schedule, edition label or retrieval time is not proof that exact original values were '
  'published before a cutoff.',
  'Official actual release evidence, precision, timezone and an independently reviewed '
  'conservative cutoff rule.',
  ('No actual or simulated publication ordering is selected.',
   'The draft release record contains only questions about first publication and the cutoff; it '
   'includes no invented official timestamp or clock assertion.',
   'Publication ordering for toy-first-issue and toy-correction-issue remains unresolved around '
   'toy-decision-cutoff despite the fictional decision review.',
   'The simulated toy-source-ledger-A orders first publication of toy-first-issue before '
   'toy-decision-cutoff and publication of toy-correction-issue after it. Relative labels convey '
   'the lesson; there are no actual dates or official release records.',
   'The worked release record repeats the simulated ordering: toy-first-issue before '
   'toy-decision-cutoff, toy-correction-issue after and excluded at that cutoff. Relative ordering '
   'is a fictional premise, not official publication evidence, timestamp precision or clock '
   'authority.')),
 ('Revision chain',
  'Corrections can change which values support a claim, so review must retain superseded issues '
  'and lineage.',
  'Authentic revision and supersession records with differences and lineage to the exact values '
  'used.',
  ('No issue relationship or supersession record is selected.',
   'The draft distinguishes a possible first issue from a correction but contains no supported '
   'supersession chain.',
   'The source revision chain remains unresolved at teaching-revision-A; the exact package '
   'revision does not supply missing source history.',
   'The invented toy-correction-issue clarifies the Appointment Information label after '
   'toy-decision-cutoff. It changes only the later toy current view; toy-first-issue is retained '
   'separately and the correction is not backfilled.',
   'The worked lineage retains toy-first-issue and toy-correction-issue separately. The later '
   'correction clarifies Appointment Information only after toy-decision-cutoff, changes the later '
   'toy view, and is never backfilled into the earlier issue or cutoff record.')),
 ('Feature and dependency lineage',
  'A timely source file does not establish that every derived input was available or eligible at '
  'that origin.',
  'Per-value and per-origin dependencies, transformations, permitted information and independent '
  'eligibility review.',
  ('No source-dependent planning description is qualified.',
   'The draft planning note refers to the proposed Directions, Form Guidance and Appointment '
   'Information meanings. Their source-bound definitions and availability are still unqualified.',
   'The same category descriptions remain unqualified inputs while definitions, rights and issue '
   'ordering are unresolved; a reviewed purpose cannot fill those dependencies.',
   'The invented toy-planning-package-A input-description record binds Directions, Form Guidance '
   'and Appointment Information to toy-category-dictionary-A and toy-first-issue at '
   'toy-decision-cutoff. Toy-correction-issue is excluded because its simulated publication is '
   'later.',
   'The worked dependency record binds the same invented category descriptions to '
   'toy-category-dictionary-A and toy-first-issue before toy-decision-cutoff. Toy-correction-issue '
   'is after the cutoff and excluded; these are descriptions, not fitted features, admitted data '
   'or validation results.')),
 ('Independent source review',
  'A self-prepared note cannot establish authenticity, independence or an accepted reviewer remit.',
  'An attributable qualified appointment, conflict assessment, exact-revision review and '
  'source-admission disposition.',
  ('No independent source reviewer or review record is selected.',
   'The proposed fictional Review Circle has no Drafting Circle or delivery role. Its '
   'source-checklist remit, competence assumptions, conflict disclosures and exact revision still '
   'need a fictional review record; no real reviewer is appointed.',
   'The fictional Review Circle reviews teaching-revision-A separately from the Drafting Circle, '
   'discloses overlap and requires recusal and replacement. Its remit records unresolved '
   'definitions, rights and vintages; it neither authenticates sources nor grants admission.',
   'The fictional Review Circle note covers toy-source-ledger-A at teaching-revision-A, with no '
   'Drafting Circle or delivery role, disclosed overlap and recusal and replacement. Its remit '
   'checks the invented definition, rights and issue links, not authentic source origin or real '
   'admission.',
   'The worked fictional Review Circle note names toy-source-ledger-A and teaching-revision-A, '
   'states its source-checklist remit and assumed competence, and separates it from Drafting '
   'Circle and delivery work. Overlap requires recusal and replacement; no authentic appointment, '
   'source authentication or real admission follows.')))

_GAP_FACTORS = (('G01',
  'Attributable real scope decisions, authenticated core appointments, accepted remits and '
  'exact-revision governance reviews.',
  ('The fictional Service Planning Office has unanswered scope and role questions.',
   'The Service Planning Office draft is a discussion-only Information Desk Capacity Review using '
   'toy-planning-package-A, with proposed Drafting Circle remits and a separate Review Circle. '
   'None is an actual agency decision.',
   'The fictional Review Circle note for teaching-revision-A covers the Planning Circle discussion '
   'purpose, exclusions and separate Drafting Circle remits; it contains no real appointment or '
   'accepted scope.',
   'The same fictional scope and role separation remain fixed while toy-source-ledger-A adds '
   'synthetic traceability. No source link appoints a person or widens the purpose.',
   'The worked fictional record fixes the Service Planning Office discussion-only scope, '
   'toy-planning-package-A, Planning Circle conditions and separate Drafting Circle and Review '
   'Circle remits. All actual appointments and scope decisions remain pending.')),
 ('G02',
  'Accountable prospective practical criteria, benefit and harm rationale, credible alternatives '
  'and independent exact-revision review.',
  ('No benefit, harm or alternative decision is selected for the fictional case.',
   'The draft names clearer category discussion as the hoped-for benefit, definition confusion and '
   'staffing overreliance as harms, and current manual notes or no package as alternatives. No '
   'measured benefit or threshold is chosen.',
   'The fictional Review Circle records the same qualitative rationale at teaching-revision-A, '
   'with discussion-only use and a pause on definition mismatch or missing lineage. It supplies no '
   'numerical rule or scientific acceptance.',
   'The same rationale is attached to the toy lineage, which can explain origin limits but cannot '
   'prove benefit, tolerable harm or superiority to manual notes or no package.',
   'The worked criteria record contains that qualitative benefit, harm, alternative and pause '
   'rationale, tied to teaching-revision-A and fictional Review Circle review. It contains no '
   'threshold, evaluated outcome, accepted practical margin or real approval.')),
 ('G03',
  'Authentic definitions and artifact-specific reuse evidence, resolved discrepancies and '
  'independent source eligibility or admission.',
  ('The fictional category definitions and reuse conditions are unresolved.',
   'The draft proposes Directions, Form Guidance and Appointment Information while the broader '
   'label Guidance remains unresolved. No terms record or source admission is supplied.',
   'The Review Circle decision note leaves the candidate Guidance definition and artifact-specific '
   'rights unresolved; a settled fictional purpose does not qualify those sources.',
   'The invented toy-category-dictionary-A separates Guidance from the three defined categories. '
   'Toy-teaching-terms-A is limited to the fabricated dictionary and issue descriptions for '
   'Planning Circle teaching, with no onward sharing or real permission.',
   'The worked source record combines the same invented dictionary, narrow teaching terms, '
   'discrepancy treatment and fictional source-checklist review. It admits no real source and '
   'supplies no authentic definitions, reuse permission or independent admission.')),
 ('G04',
  'Authentic original bytes, actual release evidence, traceable revisions and independent '
  'qualification for each value and origin.',
  ('No original issue or cutoff ordering is selected.',
   'The draft labels toy-first-issue, toy-correction-issue and toy-decision-cutoff but supplies no '
   'release ordering or authentic original bytes.',
   'The fictional review of teaching-revision-A does not establish when either toy source issue '
   'was available; original availability remains unresolved.',
   'The invented toy-source-ledger-A places toy-first-issue before toy-decision-cutoff and '
   'toy-correction-issue afterward. The first issue is eligible only under the lesson assumption, '
   'the correction is excluded at the earlier cutoff, and both remain retained.',
   'The worked lineage binds invented category descriptions to toy-first-issue before '
   'toy-decision-cutoff. Toy-correction-issue arrives after and is excluded there, never '
   'backfilled; no authentic historical bytes, release evidence or eligibility review is '
   'supplied.')),
 ('G05',
  'Preserved original adverse findings and, for a distinct later claim, a justified proposal with '
  'suitable evidence and prospective review.',
  ('The original adverse finding remains preserved and no replacement claim is proposed.',
   'Toy-planning-package-A is a teaching note with no performance claim. Any distinct later '
   'scientific proposal would need its own identity and prospective evidence, without changing the '
   'original adverse result.',
   'The fictional Review Circle note states that the discussion-only teaching package cannot turn '
   'the completed adverse finding into success. No replacement evaluation is conducted.',
   'The toy source lineage is fabricated teaching material, so its traceability establishes no '
   'usefulness and supports no empirical performance claim.',
   'The worked proposal record identifies toy-planning-package-A as a teaching note, discloses the '
   'original adverse outcome and records the evidence and review prerequisites for any distinct '
   'later claim. It reports no benchmark or scientific success and preserves the real fail result '
   'and twelve null findings.')),
 ('G06',
  'Eligible target-setting validation, prior-knowledge and dependence analysis, justified '
  'inference assumptions and independent review.',
  ('No future, population or person-level validity is supported by the lesson.',
   'The draft claim is limited to human discussion of invented categories. It records no forecast, '
   'population or person-level validity claim and no eligible validation.',
   'The fictional scientific remit and separate Review Circle distinguish that discussion purpose '
   'from inference, with prior knowledge, dependence and selection questions left as real evidence '
   'requirements.',
   'Toy-first-issue and toy-correction-issue remain fabricated history rather than untouched '
   'target-setting validation, even when their timing links are internally consistent.',
   'The worked evidence-eligibility record classifies the toy issues as fabricated teaching '
   'material and explicitly withholds future, population and person-level validity claims. The '
   'checklist records assumptions and independent-review requirements, not validation success or a '
   'replacement for the real unsupported findings.')),
 ('G07',
  'Defined protected scope, lawful authority, recipient conditions and authoritative cumulative '
  'disclosure history with accountable review.',
  ('No protected scope, permission or disclosure account is selected.',
   'The draft contains invented category-period descriptions only, with no protected-data use or '
   'privacy allowance. Unknown disclosure history blocks any extension beyond the lesson.',
   'The fictional review records synthetic-only discussion and no protected-data authority. '
   'Unknown prior history is not treated as unused allowance.',
   'Toy-source-ledger-A is an invented source chronology, not an authoritative cumulative '
   'disclosure account. The no-protected-data and no-allowance limits remain unchanged.',
   'The worked protected-scope record contains only invented category-period descriptions, no '
   'guarantee, allowance or protected-data permission, and a stop on unknown history for any '
   'extension. It supplies no authoritative real disclosure account or agency acceptance.')),
 ('G08',
  'Accepted real identity, build provenance, worker isolation and exact-environment evidence with '
  'accountable infrastructure decisions.',
  ('No build, identity or isolation record is selected for the fictional package.',
   'The draft package is a static read-only planning note for the fictional Planning Circle, not '
   'an executable model or production service. Identity, build and isolation questions remain '
   'unqualified.',
   'The fictional review note binds the static teaching package to teaching-revision-A but does '
   'not qualify a real identity, build chain, worker or environment.',
   'The same static package and exact revision are distinguished from toy source revisions. Source '
   'consistency supplies no identity, build or runtime-isolation qualification.',
   'The worked package-description record identifies toy-planning-package-A at teaching-revision-A '
   'as a static teaching note for the fictional Planning Circle. Its identity, build and isolation '
   'checklist explicitly records that no real executable, worker or production environment is '
   'qualified.')),
 ('G09',
  'Independent custody, authoritative current state and demonstrated capture or enforcement across '
  'every actual delivery route.',
  ('No independent custody, current authority or route coverage is selected.',
   'The draft proposes fictional Drafting Circle custody and a read-only Planning Circle '
   'discussion route. It establishes no independent control, authoritative current state or '
   'complete delivery coverage.',
   'The fictional review note distinguishes local record consistency from independent custody, and '
   'treats any retained recipient copy as outside a promise of automatic revocation.',
   'Toy-source-ledger-A links invented custodian and issue labels only. It has no independent '
   'administrator, authoritative current-state receipt or evidence covering actual delivery '
   'routes.',
   'The worked custody record names only the fictional Drafting Circle data remit and read-only '
   'Planning Circle teaching route. It explicitly lacks independent custody, real current '
   'authority and complete-route evidence, and makes no promise to revoke retained or downloaded '
   'recipient copies.')),
 ('G10',
  'Accepted workload and cost evidence, operating owners, justified service and recovery '
  'objectives and retirement obligations.',
  ('No operating envelope or service commitment is selected.',
   'The draft context is a static internal teaching session with human review effort and '
   'stewardship considerations, no measured workload, service target or recovery promise.',
   'The fictional review keeps Drafting Circle stewardship and a discussion-only session; it '
   'accepts no real operating objective, capacity or availability claim.',
   'Toy-correction-issue causes a fictional source-review pause without a workload or recovery '
   'test. The teaching context remains a static discussion.',
   'The worked operating record names Drafting Circle stewardship of a static Planning Circle '
   'session, a pause on changed sources and lesson-only note-retirement reasoning. It contains no '
   'workload result, production service commitment, availability promise, recovery commitment or '
   'deletion of real evidence.')),
 ('G11',
  'Qualified independent acceptance, prerequisite evidence, authorized restricted pilot and '
  'attributable handover decisions.',
  ('No acceptance, pilot or handover is selected.',
   'The draft handover boundary is no operational use: a later real pilot would need authentic '
   'prerequisites, qualified review and authorization not present in this lesson.',
   'The fictional Review Circle note leaves the teaching gate held because sources are unresolved; '
   'reviewed discussion choices do not authorize a pilot.',
   'The gate remains teaching-only despite the invented dictionary and source ledger. Synthetic '
   'traceability cannot supply authentic prerequisites or independent real acceptance.',
   'The worked fictional handover note states teaching-only, no operational use and no pilot. Its '
   'prerequisite checklist identifies authentic evidence and attributable real acceptance still '
   'missing; no actual gate passes or model delivery begins.')),
 ('G12',
  'Current authentic publication and review receipts, attributable governance decisions and '
  'exact-revision reconciliation.',
  ('No publication, governance or exact-revision receipt is selected.',
   'The draft receipt list distinguishes needed real review, publication and governance records '
   'from the existence of a locally prepared lesson.',
   'The fictional review note names teaching-revision-A and unresolved real receipt categories; it '
   'is not evidence of an actual external review, publication or governance event.',
   'Toy-source-ledger-A is unrelated to authentic publication, merge or agency acceptance '
   'receipts. The fictional record remains bound to teaching-revision-A.',
   'The worked fictional review index ties its teaching-note descriptions to teaching-revision-A '
   'and separately lists absent authentic publication, independent review and governance receipts. '
   'It invents no names, signatures, official receipts, publication events or real acceptance.')))

_SUMMARIES = ('The fictional Service Planning Office starts with unanswered scope, role and source questions '
 'for toy-planning-package-A and a possible Planning Circle discussion. All real agency decisions '
 'remain pending; no authentic source record is included.',
 'The fictional Service Planning Office drafts a discussion-only Information Desk Capacity Review '
 'using toy-planning-package-A at teaching-revision-A, invented Directions, Form Guidance and '
 'Appointment Information categories, and a Planning Circle teaching recipient. Drafting Circle '
 'remits and a separate Review Circle are proposed; sources and real authority remain unresolved.',
 'The same fictional Service Planning Office case now has a Review Circle note for '
 'teaching-revision-A, separate from Drafting Circle and delivery roles, with remit, conflict and '
 'recusal conditions. Human discussion by the Planning Circle remains the only use; definitions, '
 'rights and original vintages are unresolved. No actual agency acceptance or authentic source '
 'record is supplied.',
 'The fictional Service Planning Office case retains toy-planning-package-A at teaching-revision-A '
 'and the same Planning Circle discussion. Toy-category-dictionary-A, toy-teaching-terms-A and '
 'toy-source-ledger-A now supply concrete invented links: toy-first-issue precedes '
 'toy-decision-cutoff, while toy-correction-issue follows it and is excluded there. Traceability '
 'is simulated, not authentic source evidence or real permission.',
 'The complete worked fictional Service Planning Office record uses toy-planning-package-A at '
 'teaching-revision-A for Planning Circle discussion of invented Directions, Form Guidance and '
 'Appointment Information categories. Separate Drafting and Review Circles, narrow teaching terms '
 'and the first-issue/correction lineage illustrate all twelve checklists, including explicit '
 'blocks where authentic prerequisites are absent. No real condition is met, scientific success '
 'reported or agency approval granted.')

_OBJECTIVES = (('Separate missing decisions from missing evidence.',
  'Identify accountable roles and unanswered scope questions.',
  'Recognize that local preparation does not close the original gaps.'),
 ('Connect a fictional purpose to users, harms and responsibilities.',
  'Distinguish proposed remits from authenticated appointments.',
  'Keep source and authority questions visible while drafting.'),
 ('Distinguish decision maturity from source-evidence quality.',
  'Explain why reviewed purpose cannot repair unresolved definitions, rights or vintages.',
  'Describe reviewer remit, conflicts, separation and exact-revision binding.'),
 ('Trace fabricated original issues, later corrections and dependency descriptions.',
  'Distinguish byte identity, original availability and source authenticity.',
  'Explain why invented teaching terms and a simulated ledger grant no real permission.'),
 ('Walk through reasoning and evidence categories for every original gap.',
  'Distinguish illustrated checklists from demonstrated scientific or operational conditions.',
  'Identify authentic records and accountable decisions still required for real use.'))

_GUIDANCE = ({'do': ['List unknown scope, role and source questions explicitly.',
         'Keep the real captured record pending and unchanged.',
         'Separate questions needing decisions from questions needing authentic evidence.'],
  'dont': ['Do not read a blank worksheet as approved scope.',
           'Do not assign real people or invent original source records.',
           'Do not fill unknowns with plausible-looking facts.'],
  'next_questions': ['Who could actually make each decision?',
                     'Which source definitions and rights remain unresolved?',
                     'What authentic receipt would answer the next question?']},
 {'do': ['Label proposed choices as drafts and give reasons.',
         'Describe concrete users, harms and alternatives for the fictional purpose.',
         'Record evidence still needed for roles, sources and authority.'],
  'dont': ['Do not turn a proposed role into an appointment.',
           'Do not choose practical thresholds from observed results.',
           'Do not assume a publicly accessible file is reusable for every purpose.'],
  'next_questions': ['Does the purpose identify a decision rather than a broad capability?',
                     'Which proposed choice lacks an accountable decision maker?',
                     'Would different source definitions change the draft?']},
 {'do': ['Use fictional review to expose unresolved assumptions.',
         'Keep definitions, rights and vintages as separate evidence questions.',
         'Explain the reviewer remit, conflicts, separation and exact revision.'],
  'dont': ['Do not substitute fictional review for agency acceptance.',
           'Do not infer original availability from current publication or retrieval dates.',
           'Do not treat a reviewer label as proof of independence.'],
  'next_questions': ['Which unresolved source issue blocks reliance first?',
                     'Does permission apply to the exact artifact and use?',
                     'What record would establish authentic original availability?']},
 {'do': ['Retain synthetic first issues and corrections separately.',
         'Explain the limits of every simulated provenance or rights record.',
         'Bind toy inputs to the issue available at the fictional origin.'],
  'dont': ['Do not call the fabricated ledger an official archive.',
           'Do not equate traceability with authentic custody or legal permission.',
           'Do not backfill later corrections or treat synthetic history as untouched validation.'],
  'next_questions': ['Which links demonstrate local consistency only?',
                     'What independent evidence would authenticate the real source?',
                     'How would a correction affect the applicable decision record?']},
 {'do': ['Read each illustrated gap with its remaining real receipt.',
         'Explain rationale, conflicts and review scope behind fictional decisions.',
         'Preserve all real adverse and unsupported findings unchanged.'],
  'dont': ['Do not submit tutorial configurations as operational agency responses.',
           'Do not call an illustrated checklist a passed scientific or production condition.',
           'Do not invent names, signatures, performance results or authentic publication records.'],
  'next_questions': ['Which parts still need an actual accountable decision?',
                     'Which authentic source or independent review records are absent?',
                     'What would make an illustrated condition applicable to a different real scope?']})

_STATUS_ROWS = (('not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started',
  'not_started'),
 ('draft_illustration',
  'draft_illustration',
  'not_started',
  'not_started',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration',
  'draft_illustration'),
 ('review_illustration',
  'review_illustration',
  'draft_illustration',
  'not_started',
  'draft_illustration',
  'draft_illustration',
  'review_illustration',
  'draft_illustration',
  'draft_illustration',
  'review_illustration',
  'draft_illustration',
  'review_illustration'),
 ('review_illustration',
  'review_illustration',
  'source_trace_illustration',
  'source_trace_illustration',
  'draft_illustration',
  'draft_illustration',
  'review_illustration',
  'draft_illustration',
  'draft_illustration',
  'review_illustration',
  'draft_illustration',
  'review_illustration'),
 ('worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration',
  'worked_illustration'))

_STATUSES = frozenset(("not_started", "draft_illustration", "review_illustration", "source_trace_illustration", "worked_illustration"))
_ROOT_KEYS = frozenset(("schema", "id", "title", "summary", "fictional_example", "public_synthetic_only", "authentic_source_records_included", "real_agency_decisions", "original_substantive_gaps_closed", "authorization_effect", "benchmark_executed", "learning_objectives", "simulated", "guidance"))


def _require(condition):
    if not condition:
        raise ValueError("Invalid fixed tutorial configuration")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _text_list(value):
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def _validate(config, selected):
    _require(isinstance(config, dict) and set(config) == _ROOT_KEYS)
    _require(config["schema"] == "local-fictional-decision-evidence-tutorial/1")
    _require(config["id"] == selected and config["title"] == dict(SCENARIO_OPTIONS)[selected] and _text(config["summary"]))
    _require(config["fictional_example"] is True and config["public_synthetic_only"] is True and config["authentic_source_records_included"] is False)
    _require(config["real_agency_decisions"] == "pending" and type(config["original_substantive_gaps_closed"]) is int and config["original_substantive_gaps_closed"] == 0)
    _require(config["authorization_effect"] == "none" and config["benchmark_executed"] is False and _text_list(config["learning_objectives"]))
    simulated = config["simulated"]
    _require(isinstance(simulated, dict) and set(simulated) == {"decision_configuration", "source_configuration", "gap_walkthrough"})
    for key, factors in (("decision_configuration", _DECISION_FACTORS), ("source_configuration", _SOURCE_FACTORS)):
        rows = simulated[key]
        _require(isinstance(rows, list) and len(rows) == len(factors))
        for row, factor in zip(rows, factors):
            _require(isinstance(row, dict) and set(row) == {"factor", "choice", "reason", "evidence_needed"})
            _require(row["factor"] == factor[0] and all(_text(value) for value in row.values()))
    rows = simulated["gap_walkthrough"]
    _require(isinstance(rows, list) and len(rows) == 12)
    for number, row in enumerate(rows, 1):
        _require(isinstance(row, dict) and set(row) == {"id", "status", "reason", "real_receipt_needed"})
        _require(row["id"] == f"G{number:02d}" and row["status"] in _STATUSES and _text(row["reason"]) and _text(row["real_receipt_needed"]))
    guidance = config["guidance"]
    _require(isinstance(guidance, dict) and set(guidance) == {"do", "dont", "next_questions"} and all(_text_list(value) for value in guidance.values()))


def _make_scenarios():
    scenarios = {}
    for position, (identifier, title) in enumerate(SCENARIO_OPTIONS):
        config = {
            "schema": "local-fictional-decision-evidence-tutorial/1",
            "id": identifier,
            "title": title,
            "summary": _SUMMARIES[position],
            "fictional_example": True,
            "public_synthetic_only": True,
            "authentic_source_records_included": False,
            "real_agency_decisions": "pending",
            "original_substantive_gaps_closed": 0,
            "authorization_effect": "none",
            "benchmark_executed": False,
            "learning_objectives": list(_OBJECTIVES[position]),
            "simulated": {
                "decision_configuration": [{"factor": factor, "choice": choices[position], "reason": reason, "evidence_needed": receipt} for factor, reason, receipt, choices in _DECISION_FACTORS],
                "source_configuration": [{"factor": factor, "choice": choices[position], "reason": reason, "evidence_needed": receipt} for factor, reason, receipt, choices in _SOURCE_FACTORS],
                "gap_walkthrough": [{"id": gap_identifier, "status": _STATUS_ROWS[position][index], "reason": reasons[position], "real_receipt_needed": receipt} for index, (gap_identifier, receipt, reasons) in enumerate(_GAP_FACTORS)],
            },
            "guidance": deepcopy(_GUIDANCE[position]),
        }
        _validate(config, identifier)
        scenarios[identifier] = config
    return scenarios


_SCENARIOS = _make_scenarios()


def scenario_config(id=None):
    """Return a fresh fixed lesson; unknown identifiers never reflect input."""
    selected = DEFAULT_SCENARIO_ID if id is None else id
    if not isinstance(selected, str) or selected not in SCENARIO_IDS:
        raise ValueError("Unknown tutorial scenario")
    config = deepcopy(_SCENARIOS[selected])
    _validate(config, selected)
    return config


def scenario_json(id=None):
    """Canonical UTF-8 teaching JSON, never an operational intake response."""
    return (json.dumps(scenario_config(id), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
