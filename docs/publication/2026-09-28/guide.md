# Model releases and agency workflows

A practical guide for agency teams and policymakers

Updated 28 September 2026

This guide explains what the project findings mean for the way an agency plans, buys, trains, approves, shares and maintains AI models. Its central recommendation is to connect those existing activities through one release record, compare reuse before commissioning new protected-data work, and make each approval specific to the information people will actually receive.

The proposed arrangements are for a bounded validation pilot. They preserve a route to useful releases while testing the evidence, controls and operating effort needed for wider adoption. Existing agency requirements continue to apply.

Read Chapter 1 for the findings and their practical meaning, Chapter 2 for changes to existing work, and Chapter 3 for the updated release flow. Chapters 4 and 5 cover pilot decisions and worked examples. The release brief at the end can be used in an existing approval pack.

Detailed calculations and implementation material sit in the technical companion. The separate experimental supplement preserves every reported model setting and result table, including negative findings and later corrections. This reader guide does not require a technical background.

## Executive summary

This guide helps agencies decide how a useful model can be developed, shared and maintained with appropriate privacy protection. It connects that decision to familiar work: service planning, procurement, data access, technical testing, approval, supplier management and incident response.

The findings support three practical changes. First, compare a proposed model with public information and existing approved outputs before commissioning new work on protected data. Some tested designs improved predictions; others added little or performed worse than simpler alternatives. Second, assess everything recipients can combine, including older models and shared datasets. Third, require evidence for the particular release: useful predictions and unsuccessful attacks do not by themselves establish privacy protection.

Removing names remains useful. It does not remove every identifying pattern or sensitive inference, so the release review must also consider the remaining information and the recipient’s access.

The proposed process is suitable for a bounded validation pilot. It does not replace existing agency authority or establish that the research prototypes are ready for operational deployment. Begin with one use case, named owners and controlled delivery. Test whether the process identifies useful options, produces defensible decisions and handles changes reliably. The companions preserve the complete research results and their limitations.

For policymakers, the immediate decisions are to define the pilot scope, assign the owner of the common release history, agree what evidence an approval requires, and measure the operating burden before wider adoption. The proposal is to add these checks to existing work, with clear responsibility for each hand-off.

## 1 What the findings mean for an agency

The research supports a more connected release decision. A useful model may still disclose information that should remain protected. A narrowly designed output may meet the service need with less disclosure, and information already approved for release may avoid another round of protected-data work. The evidence also shows where additional complexity did not produce a practical benefit.

### Why removing names is only a starting point

Removing names and direct identifiers reduces an obvious route to identification. Other information may remain distinctive: a rare diagnosis, unusual work history, location pattern or combination of attributes can be matched against information held elsewhere. A stable replacement code helps the agency link the same person's contributions, but it does not make those contributions anonymous.

A trained model can also expose information from its source. It may reproduce an unusual passage, respond differently because a particular record was used, or help a recipient infer a sensitive fact. Access to the model's internal files, repeated queries and previously shared outputs can create different opportunities to learn that information. A confidentiality clause supports accountability, but the reviewer still needs evidence for the actual access.

For the agency, this changes the hand-off after data preparation. “Names removed” should be recorded as a control performed, rather than used to end the privacy review. The next questions are what remains in the data, what the model or service can reveal, what recipients already know, and what earlier outputs they can combine.

### Be clear about what needs protection

Three questions should be kept distinct. Could someone work out who a record or model response concerns? Could they learn that a person was included in the underlying data? Could they infer a sensitive fact about that person? Evidence addressing one question does not automatically answer the others.

The current central research implementation assumes a fixed registered population and protects changes to recorded values under its stated conditions. An agency that needs to protect whether someone took part must obtain evidence covering that different question. The same person's multiple records also need to be considered together; protecting one record is not automatically protection for everything that person contributed.

The findings below translate the full experimental record into decisions for an agency. They distinguish results demonstrated within the studies from actions proposed for the pilot.

### 1 Assess what the recipient actually receives

The tests found different exposure from model files, ordinary prediction services and scores linked to particular records. Some nearest-neighbour model files retained the input patterns they used. Recovering a pattern did not by itself prove a person's identity or participation, but it showed why a file export needs a different review from ordinary queries.

Agency action. Replace “share the model” with a description of the actual files, outputs and access. Include supporting data, explanations and logs. The approving officer should know which of these will leave the agency and which controls the assessment relies on.

### 2 Judge models by the service result

The model studies produced mixed results. Additional training improved the measured predictive performance of GPT-2 in its study, while the tested Qwen runs worsened their corresponding measure. Other model runs had incomplete training or warnings. These results do not form a league table across different tasks.

Agency action. Procurement and development should require evidence for the intended service and configuration. Compare the proposed model against a competent simple alternative, retain failed runs and warnings, and do not use model size or a completed training job as a proxy for benefit.

### 3 Test whether the task can be achieved before extending the work

Several candidates failed the usefulness requirement even with more records, longer training or access to the unprotected research inputs. A later corrective study also failed its specified task requirement. These failures identify limits of the tested designs; they do not show that every possible approach will fail.

Agency action. Agree the minimum useful result before testing. If a properly permitted benchmark cannot meet it, reconsider the task, data or design before commissioning further privacy engineering. Keep the final evaluation independent and make any changed target explicit.

### 4 Require a reason to use more protected information

Public-information and omitted-field alternatives often matched or beat more elaborate private methods. Other controlled studies found useful gains in particular settings. In the paper's real-data evaluation, its specialised model-update method matched reuse and trailed a stronger public learner. The case for additional protected-data use therefore depends on the task and the comparison.

Agency action. Add public information, existing outputs and simpler inputs to the business case. Give those alternatives a fair evaluation. Choose new protected-data work only when the expected improvement justifies it and the proposed release can meet the required safeguards.

### 5 Treat useful reuse as a successful outcome

Several studies produced further models or outputs from a source whose privacy exposure had already been accounted for. In some comparisons, capable reuse matched a more elaborate joint method. The benefit came from using the existing source well, rather than making another protected computation.

Agency action. Maintain an inventory of approved reusable results. Check whether one can meet a new team's need, retain its original history and verify the new access. Repeating delivery of a stored result differs from running the private computation again; the latter needs its own justification.

### 6 Plan related tasks before the first release

Carefully specified small-model studies showed that planning a later release around an earlier one can improve results over independently adding another release. Those results depend on knowing how the earlier model was produced and preserving what recipients actually received.

Agency action. Programme teams should identify anticipated tasks early. The current executable research route fixes the possible tasks and methods before protected work and uses unchanged data. It cannot be assumed to cover an unforeseen task, new labels or arbitrary model files already outside the agency. Specialists must establish a supported route for those cases.

### 7 Keep only inputs that contribute to the purpose

In the studies of multiple attributes, adding protected fields or spreading the privacy allowance evenly did not reliably improve prediction. A carefully selected field sometimes matched a much broader search. Protecting one field also did not establish protection for participation or every other sensitive fact.

Agency action. Make data minimisation part of model design. Compare leaving a field out with using it under protection. Record why each retained input is needed and ensure that choosing the inputs and testing the choice are themselves covered by the assessment.

### 8 Include model selection and testing in the review

Information can be disclosed through the choice of model, task or reported result, even when each candidate has its own privacy evidence. A visible refusal can also convey information. The research supports covering the complete selection-and-release process.

Agency action. The technical work order should specify how choices and evaluations are made. Use public information or an appropriately protected procedure. Do not let informal decisions based on confidential test results fall outside the release record.

### 9 Follow the same people across teams and versions

Reliable records of which people appeared in which sources allowed some useful releases that a less precise assessment refused. Where all sources concerned the same people, the stricter result remained. Both an exact ledger and a dependency graph reached the same decisions when supplied with the same evidence.

Agency action. Give the data steward responsibility for links between people and their contributions across projects. Carry earlier disclosures forward when names, versions or recipients change. Accurate records matter more than choosing a particular database or diagramming approach.

### 10 Separate a passed test from permission to release

The tree, image and language-model screening results identified concerns but did not establish sufficient general privacy limits for clearance. Some controlled finite studies could distinguish useful options that cleared, options that exceeded limits and cases needing more evidence. Software tests that passed confirmed specified behaviour, not an agency release approval.

Agency action. Give the approving officer a clear outcome for each required privacy question: supported clearance, demonstrated excessive exposure or an unresolved gap. Failed attacks alone should not be presented as proof of safety. A hold should name the evidence or design change needed next.

### 11 Connect the approval to actual delivery

Local implementation checks exercised repeated requests, concurrent requests, failures, saved outputs and revocation. They showed how bounded controls can keep delivery tied to the assessed computation. They did not establish a deployed government service or prove that every real export is captured.

Agency action. Link the approved record to training and delivery systems. Test that retries do not silently produce extra results, that two teams cannot reserve the same remaining allowance, and that the operator checks current authority before each delivery. Include these checks in the pilot's operational acceptance criteria.

### 12 Handle deletion and retained copies separately

One controlled study updated a particular statistical model after removing known contributions and matched its specified retraining method. That result is limited to the tested setting. Changes to the current model did not erase older models already held by recipients, and replacement performance still required evaluation.

Agency action. A deletion or retraining request should address removal from the current system, usefulness of the replacement and earlier disclosures. Record all three. Revoking future access and keeping the past release history are compatible actions; neither implies that an external copy has disappeared.

### 13 Buy infrastructure for demonstrated operating needs

The studies found no general speed advantage for a graph over an exact ledger. Some large bookkeeping and sampling exercises worked, while certain model optimisations remained expensive or timed out. Faster repeat verification did not remove the need to check current release authority.

Agency action. Compare systems against the pilot's actual volume, review time, concurrency and audit needs. Distinguish record keeping from model training and specialist verification. Reuse completed technical checks only where their inputs still match, and keep current access checks in place.

### 14 Be explicit about what the evidence does not yet cover

The archive combines fitted models, small mathematical examples, software exercises and illustrative decisions. It does not establish a project-wide approval for every kind of AI. For example, this inventory does not contain a completed project diffusion-model or audio-model study. Published research about those areas is a separate source of evidence.

Agency action. Maintain a short register of supported uses, missing evidence and next validation steps. Commission a specific test or control for each gap. Treat the successful planning example in Chapter 5 as an illustration of an approval route, while requiring the actual agency proposal to supply its own evidence.

These fourteen findings cover the 51 study sections through the companion's findings-to-actions map. It identifies the source for each conclusion, retains favourable and adverse results, and separates later diagnostic work from the original evaluations.

## 2 What changes in everyday agency work

Connect the model release to the agency’s existing service, data, procurement and approval records. The additional work is to show what recipients can learn, how earlier releases affect the proposal and who will enforce the decision. Chapter 3 gives the sequence. This chapter explains what each team needs to add to its normal work.

### Service planning and the case for new data use

The business owner should add a comparison of public information, existing approved outputs and new protected-data work to the service proposal. Define the minimum useful improvement and what each option is allowed to know. Retain the comparison with the business case.

The studies found useful gains in some controlled settings and little benefit or worse results in others. The paper’s early public check can rule out the required gain for its specified small model families. It can therefore prevent unnecessary optimisation work; passing it does not establish approval. This is a reason to check the need before committing staff or supplier effort. [P2, P6, P7, P10]

### Procurement and supplier evidence

The procurement lead and service owner should describe the access actually needed: a model file, a controlled service or an approved aggregate. Include inputs, outputs, logs, retention, supplier use, review evidence and change notifications in the requirements and acceptance criteria.

The model tests produced different outcomes for different configurations. A familiar model name or headline accuracy is therefore insufficient evidence for the proposed service. Ask the technical assessor what supplier information and testing will be needed before the procurement is finalised. This makes that work visible in the schedule and cost estimate, rather than leaving an unspecified evidence requirement for delivery acceptance.

### Data preparation and access

The data steward should extend the data-access record to identify the people covered, repeated contributions and links to relevant earlier projects. Keep only information needed for the purpose. Remove unnecessary direct identifiers and restrict identity lookup, while preserving the internal links needed to recognise the same person across versions.

Names alone do not determine exposure: rare combinations may identify someone, and sensitive facts may be inferred without unique identification. Record whether the requested protection concerns recorded values, participation, or both. The current bounded continuation method does not establish participation protection. Uncertain identity links or contribution limits become issues to resolve before dependent work proceeds. [P6–P9]

### Approval and the next step

The assessor should prepare one release brief covering usefulness, privacy evidence, earlier disclosures and enforceable conditions. The approving officer should be able to see the recommendation, its assumptions, any unresolved question and the responsible owner without reading the experimental tables.

A successful attack can demonstrate a problem; an unsuccessful attack does not by itself establish protection. Where approving evidence is missing, assign a concrete next step: obtain evidence, narrow access, revise the method or reconsider the purpose. An unresolved result is not itself a demonstrated breach. Agree the evidence requirement early so that the team can plan the review effort and avoid discovering an unassigned task at final approval.

### Training and the approved work order

The model owner should record the approved data version, method, evaluation plan and permitted outputs before protected computation. Include selection and evaluation work in the assessment rather than treating them as unrelated preparation. Follow Chapter 3 for reservation and execution.

The bounded research method supports an agreed menu of tasks on unchanged data. Unexpected labels, changed records or a different method require fresh analysis. Put those limits in the work order and change-control record. The practical aim is to identify a changed proposal before the team spends time running a process that the original assessment does not cover. [P7–P9]

### Sharing and the combined recipient view

The sharing owner should check the recipient’s existing data and models and the outputs that covered recipients could combine. Attach that history to the release brief. Reliable overlap information allowed some useful releases that a coarse assessment refused; a graph and a ledger reached the same decisions when given the same evidence. Accurate records are the priority. [P2]

The operator should deliver the approved version through the agreed route and check current authority. In the bounded prototype, repeated delivery uses saved model bytes, not fresh unaccounted results. Reusing technical checks may reduce repeated verification, but it does not remove the current access check. [P7, P9]

### Retraining and deletion

The model owner and data steward should record what was removed from the current system, how useful the replacement is and what earlier recipients may retain. The controlled deletion study supported one specific update method; it does not establish a general deletion method for language models.

Include the removal specification, verification and affected release list in the change record. Revocation can stop future delivery but cannot recall retained information. Keep old versions linked to the same people and disclosures. Plan for this review when scheduling retraining or deletion work; a new model name does not create a fresh privacy history. [P4, P7]

### Incident response

The incident owner should know who can suspend access, preserve evidence and commission reassessment. Use the release record to identify affected versions, recipients, conditions and operational owners. New recipients, richer outputs, unexpected disclosures and material data changes may require review before continued access under an old approval. The pilot should test whether the records are complete enough to support that response. [P7, P9]

### What this means for workload and lead time

The process adds upfront work: describing access, checking history, obtaining evidence and assigning controls. Reuse and early comparison can avoid some unnecessary computation, while consistent records can support repeated reviews. The studies do not establish overall savings in agency processing time.

Record time spent on intake, missing information, technical review, rework and approval during the pilot. Also record useful proposals enabled and proposals redirected. These measures let the agency judge whether the additional assurance work is proportionate and where the process needs improvement before wider adoption.

## 3 How a release moves through the agency

The proposed pilot would add a model-sharing record to existing project, data, security and approval processes. Its purpose is to help teams deliver useful services with a clear account of what was assessed, what can be shared and who remains responsible. Start with a bounded service and named recipients; use the pilot to establish which records and controls work before expanding it.

### 1 Agree the service need and a workable standard of usefulness

The business owner describes the decision or service the model will support, who will use it and what improvement would justify the work. Agree a way to judge usefulness before examining protected data. For example, a staffing team may need a reliable demand category rather than individual records or an unrestricted model.

Impact on the existing workflow. Intake records the intended benefit and the minimum useful result alongside the proposed technology. The business owner can judge simpler alternatives against the same need.

### 2 Connect the proposal to agency data and release records

The data steward and model team map the links between source datasets, later versions, model development and previous disclosures. Include related products used by other teams and recipients who may combine information. Record whose information is involved across those sources. An unresolved overlap goes to a named owner for resolution or conservative assessment.

Impact on the existing workflow. The existing data catalogue gains links to model versions and release decisions. A new project name does not create a fresh start for information already disclosed. This shared record need not centralise all raw data.

### 3 Review the whole proposal together

A coordinating reviewer checks the proposed access, recipients, earlier disclosures and evidence with the responsible data, privacy, security and technical teams. Include development work that could reveal protected information through model choices, testing or visible decisions. Agree responsibilities and the public assessment plan before protected work begins.

Impact on the existing workflow. Reviews use one versioned proposal and a common history. Teams can resolve conflicting assumptions early, while the design remains easy to change.

### 4 Check whether an existing result can meet the need

Compare public information, an already approved result and the proposed new work against the agreed usefulness requirement. A previous forecast, restricted service or suitably protected dataset may already be sufficient. If the team proposes an update, it explains the benefit of accessing protected information again and assesses the combined effect of old and new disclosures.

Impact on the existing workflow. Reuse becomes a positive delivery option. A suitable existing result can reach another authorised team after the current access checks. New recipients, new inputs or a changed purpose still receive the assessment they require.

The paper adds an early check for its specified small model families: using the public task description, specialists can sometimes show that even unrestricted information could not improve enough on reuse. In that case, stop that adaptation route and consider approving a useful existing result. Passing the check only leaves further improvement possible; it does not clear a release. The conclusion depends on the declared public assumptions about the data and task and applies only to the stated model family.

### 5 Fix the design before the protected work

When new work is justified, the technical team selects and checks the actual approved methods and permitted outputs before accepting protected inputs. The plan covers how any later choice between outputs will be made. In the proposed pilot, the shared privacy account reserves the agreed allowance before the covered computation starts. Any planned later update must be included in the applicable assessment. The privacy account records cumulative permitted exposure from releases; the specialist assessor supplies the charge against the agency's agreed limit.

For the paper's specific research route, the actual methods for the first and later models are fixed and checked before protected input or reservation. Reserve enough allowance for their complete shared history before producing the first model. The later task comes from the agreed menu, its protected labels already exist, and the data remain unchanged. Retain an already shared model exactly as delivered; this prospective procedure cannot retrospectively approve an unsupported earlier release.

Impact on the existing workflow. Teams obtain clearance for the work they will actually run. Changes discovered during development return to the agreed change process. The technical companion explains the evidence needed for specific methods and the limited settings supported by current prototypes.

### 6 Record the decision and deliver the approved result

The team executes the agreed work and checks the frozen candidate against the task requirement using independent public evidence or a protected evaluation included in the assessment. Privacy and usefulness each need their own supporting evidence. For the bounded update route, a later model is produced using the saved earlier result and the unchanged protected data; another request receives the committed result rather than a fresh draw.

The decision can approve reuse, approve a new release with defined conditions, request a useful redesign, or hold a named evidence gap. Record the result before delivery. The delivery service checks the approved version, recipient authority, source records and current restrictions. A retry uses the committed result where the design provides for it.

Impact on the existing workflow. Approval and delivery remain connected. Operators can see exactly what is authorised, and project teams receive a specific next step when further work is needed.

Reusing a completed technical verification does not replace these current checks. A software pass, a package fingerprint or an entry in a register also needs the supporting evidence that the approved computation and controls were actually used.

### 7 Keep approval current as the service changes

Assign an owner for new recipients, retraining, changed outputs, expiry, incidents and deletion requests. Use the dependency record to find affected releases. Revocation can stop future controlled access; earlier recipients may retain information already shared, so its history remains in the assessment.

Impact on the existing workflow. Ordinary service management carries the release conditions forward. The pilot measures useful deliveries and reuse, review effort, unresolved gaps and control failures, giving the agency evidence for its next adoption decision.

The prototype retains conservative reservations after failure or abandonment, as well as charges for earlier disclosures after revocation. Choosing reuse before reservation can avoid unnecessary additional allowance; it does not return allowance already committed. The companion preserves the exact rules and their limits. [P7–P10]

## 4 Run a pilot through existing agency governance

The proposed workflow should help an agency deliver useful services while making release decisions traceable. It is still being validated. The pilot should test whether the agency can operate the controls and whether their benefit justifies the additional work. It does not establish a new government-wide policy or replace existing legal, security, procurement and data-management requirements.

### Give the work to named owners

Start with the agency's existing decision rights. Agree who owns the service, the data, the technical assessment, the release decision and the delivery controls. One person may hold more than one role in a small pilot where appropriate, but the person seeking approval should not be the only person judging the evidence.

| Existing role | Additional responsibility in the pilot |
| --- | --- |
| Service or business owner | State the decision the model will support, the minimum useful result, whether existing information can meet the need and why any additional protected access is needed. Own the benefit and agreed restrictions. |
| Data owner or steward | Confirm whose information is involved, all contributions made by the same person, previous disclosures and the authority for the proposed handling. |
| Model team or supplier | Describe the actual files and service, provide evidence for the chosen design, and identify every step that uses protected data. |
| Independent assessor | Check that the evidence covers the actual release, recipients and earlier disclosures. Explain unresolved issues in decision language. |
| Privacy legal and security reviewers | Apply existing requirements and check the assumptions that depend on contracts, identity controls, hosting and recipient behaviour. |
| Authorising officer | Approve a specific use and release, ask for a stated gap to be resolved, or decline the proposal with reasons. |
| Registry and delivery operators | Keep the common history and reserved allowance consistent; enable only the authorised version and stop future access when required. |

The common history needs an accountable owner even where different teams maintain the underlying records. Before relying on it, the pilot should demonstrate that it captures actual exports, including those made through suppliers or supporting services. A technically complete diagram cannot compensate for an unrecorded disclosure.

### Begin with a manageable use case

Choose one service decision, one accountable data owner and one controlled delivery route. A planning task served by aggregate information or an existing approved output is a useful candidate. State the covered people, recipients, data versions and allowed model changes. Include the relevant earlier history even when the pilot itself is small.

Begin process rehearsals with public or appropriately approved data and controlled test outputs. A live release of protected information still requires the applicable authority and evidence. The local research tools are inputs to that decision, not a substitute for it.

Use the pilot to test the whole route. Rehearse two teams requesting access at the same time, a failed computation, a repeated download, a new recipient, a model update, expired approval and revocation. Check that the right version is delivered and that the earlier privacy account survives each event. These exercises reveal gaps between the written process and operational systems.

### Measure whether the workflow helps staff and service users

Agree pilot success criteria before reviewing the results. Measure the additional work as well as the releases enabled. A process that looks sound on paper may still be too hard to maintain or may fail to support a useful service.

| Question for the pilot | Evidence the agency should collect |
| --- | --- |
| Did the released output help the service? | Performance against the agreed task requirement and the public-data or reuse alternatives, with uncertainty explained. |
| Did the records cover what actually left the agency? | Reconciliation of the release register with delivery logs, supplier activity and retained versions. |
| Could staff reach and explain a decision? | Review time, missing information, rework, disagreements and a readable record of the reasons. |
| Did shared accounting improve coordination? | Duplicate requests detected, reuse opportunities taken and decisions changed by verified overlap between people. |
| Did delivery controls work? | Results from the retry, concurrent-request, expiry, revocation and version-change exercises. |
| Was the operating burden proportionate? | Staff effort, specialist dependencies, infrastructure costs and bottlenecks at each existing approval step. |

Keep separate outcomes for a useful release, a privacy assessment that clears, an unresolved evidence gap and a control that fails. A single overall pass rate would hide different reasons for delay and make it harder to improve the process.

### Make expansion a separate decision

At the end of the pilot, report benefits, controls demonstrated, remaining gaps and operating costs. Expand within the scope the evidence supports. The paper's tested route for a later model assumes planned tasks and unchanged data. New records, labels, purposes, model types or recipients require review and may need different controls. A successful small pilot does not automatically approve those changes.

## 5 Worked decisions for agency teams

These examples show how the findings change practical decisions. The first two are illustrative cases, not measured agency deployments. The full calculations and assumptions are retained in the technical companion. The third shows how the same questions apply to an everyday service design.

### A planning forecast is approved for reuse

A planning team needs a high-or-low forecast of next month's overall demand to choose a staffing level. It does not need a prediction about any named person. An earlier team already received a forecast produced once by a carefully specified privacy-protecting method. The proposed new release is the same stored forecast.

The team starts with the reuse check. The existing output meets the planning need, so there is no reason to access personal records again or train another model. The agency registers the earlier computation and checks that the new recipient will receive the same output, with no more detailed scores or supporting personal information.

In this synthetic teaching example, the defined privacy checks all clear and expected forecasting accuracy is about 90%, against a requirement of 75%. Those figures come from a known mathematical demand pattern. They are not a measured performance promise for a real agency. The identity and sensitive-information checks also rely on the recipient information specified in the example.

The decision is to approve this release for the stipulated staffing purpose. The delivery operator checks current authority and sends only the stored forecast. The agency keeps the original privacy charge; sending the same output again does not create a fresh computation. A new forecast, extra output detail or changed recipient knowledge would trigger another review.

Impact on the existing workflow. The service owner obtains a useful output, the data team avoids unnecessary training and the approving officer receives a clear, bounded decision. Reuse still needs authority and scope checks. The success comes from matching the information delivered to the actual planning decision.

This example protects participation as well as individual values under its own assumptions. It is separate from the paper's current fixed-population implementation, which does not establish participation protection.

### A useful health research service has one unresolved question

A team proposes exporting a model file for research on hospital readmission. The initial design reveals too much in the example's specified tests. The team assesses alternatives and finds that a controlled service returning broad categories can meet the research need. The review includes the earlier release history from the outset; comparisons of individual options are intermediate checks.

The remaining issue is specific: the evidence does not yet establish an acceptable limit on what the recipient could learn about a protected health condition. The proposal remains on hold for that gap. The team can supply evidence for the exact service and recipient, or change the design and evaluate it again. Any use of protected records for selection or testing must itself be covered by the privacy assessment.

Impact on the existing workflow. The assessor gives the project a defined next action and owner. The business owner can weigh the cost of resolving the gap against a narrower service. The result does not mean that every use of the model is unsafe or that the project must stop indefinitely.

### A case note assistant is reviewed as a whole service

An agency wants an assistant to draft summaries from confidential case notes. The supplier's base model is only one part of what needs review. Staff may submit personal information in prompts; the service may retrieve records, retain logs, attach hidden fields or send requests to another provider.

Before procurement is finalised, the service owner defines what staff need to receive. The data and security teams map where notes, prompts, drafts and logs travel, who can access them and how long they remain available. The supplier identifies whether any of that information is reused for training or passed to another service. The assessor reviews the actual settings and delivery arrangement rather than relying on a statement that the base model is public or that names were removed.

The agency then tests whether a design with limited records, controlled retrieval and restricted output can meet the drafting need. Evidence about extraction and sensitive inference should reflect the proposed service and realistic recipient access. A failed attempt to extract a case note is useful testing evidence, but does not establish that every possible attempt will fail.

Impact on the existing workflow. Procurement asks for evidence and operational controls that can be checked. Change management treats a new retrieval source, logging setting, supplier endpoint or output field as a possible change in disclosure. Incident response can trace affected records and recipients through the service record.

This is a design pathway, not an approval. A live release decision depends on the completed assessment and the agency's existing requirements.

## Appendix A A short release brief for the approving officer

Use this brief in the existing approval pack. The specialist evidence can remain in attachments, with a named owner who can explain it. The brief should allow a policymaker to understand what benefit is expected, what information may leave the agency and what decision is needed.

| Question | What the brief should say |
| --- | --- |
| What public service decision will this support? | The user, purpose, minimum useful result and expected benefit. |
| Can existing information meet the need? | The public-data and reuse options considered, and why new protected access is or is not justified. |
| Whose information is involved? | The covered people, data versions and all relevant contributions, with the responsible data owner. |
| What will recipients receive and retain? | The exact file or service, detail of outputs, supporting material, recipients and possible onward sharing. |
| What is already in the release history? | Earlier data, models, reports and outputs that recipients can combine, including retained versions. |
| What does the evidence establish? | Whether each required privacy question clears, fails or remains unresolved, and whether the output meets the task requirement. |
| What conditions make that conclusion valid? | The scope, data and model version, recipient knowledge, operating controls and any assumptions that still need verification. |
| What must happen before access starts? | Required reservation, completed assessment, institutional approval, committed release record and operator checks. |
| What will trigger another review? | Changes to data, purpose, recipients, model, supporting services or outputs; expiry, incidents and revocation. |
| What decision is requested? | Approve the defined release, resolve a named gap, or decline the proposal; state the accountable owner and review date. |

The decision should state its practical effect. For example: “Approve delivery of the stored planning forecast to the named team for the agreed period,” or “Hold the research service pending evidence about inference of the specified health condition.” Avoid replacing that explanation with a model score or an unexplained technical certificate.

## Appendix B How to use the supporting evidence

The experimental supplement retains all 238 tables and 5,543 displayed result rows across 51 study sections. These include different models, settings, repeated measurements, earlier adverse findings and corrected comparisons. A displayed row is not necessarily an independent experiment. The full source index identifies the underlying records.

The main guide translates those results into agency decisions. The supplement and frozen source files allow specialists to inspect every reported setting. The technical companion explains the calculations, formal assumptions, verification limits and implementation details. A detailed assessment reference preserves the technical background removed from the reader guide.

Use the sources for the question they can answer. A mathematical result may establish a limit within a stated model. An attack test shows what a particular method revealed under particular conditions. A local software check shows whether a bounded operation behaved as expected. None of these alone demonstrates a complete operational deployment.

The current paper, Private Model Export for New Tasks, is a working research manuscript dated 28 September 2026. Section 3 of this guide follows its updated release flow. The publication includes the top-level manuscript and selected protocol sources as dated context, together with the existing experimental archive; it does not include a complete paper compilation or experiment-reproduction environment.

### Where to find each source

| Reference in this guide | Supporting record |
| --- | --- |
| P1 | Research plan snapshot and study context. |
| P2 | Central accounting and person-level model-export studies. |
| P3 | Original bounded central gate and its implementation limits. |
| P4 | Controlled deletion and replacement study. |
| P5 | Repository status and historical implementation context. |
| P6 | Current working manuscript Private Model Export for New Tasks. |
| P7 | Current paper release protocol and information-value screen. |
| P8 | Mathematical treatment of retained outputs and later releases. |
| P9 | Execution safeguards for the bounded later-release method. |
| P10 | Later screening and reuse diagnostic with its limits. |

The local publication folder contains the guide, technical companion, detailed assessment reference, findings-to-actions map, experimental supplement and source index. References E001 to E104 identify the preserved experimental source records. The source manifest records provenance and file hashes for specialist review.
