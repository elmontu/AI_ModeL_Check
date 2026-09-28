# Model privacy and release assurance

A practical guide to useful model releases and proportionate privacy assessment

#### Scope

This guide addresses the privacy implications of releasing a trained model, an API or a related artefact. It connects model privacy to the wider data and application layers, including prompts, retrieval and logs. It is intended for Singapore public-sector business owners, technical practitioners and reviewers. Procurement and adoption of externally sourced models require additional assessment.

#### Content update 28 September 2026

This guide presents a proposed approach for a bounded validation pilot, informed by project findings through 28 September 2026. It helps teams identify useful release options and the evidence needed to support them. The current software is alpha 0.8.0; local tools and research prototypes do not provide production agency authorisation. Worked examples are illustrative, and the responsible authority would set the applicable tolerances. The complete experimental supplement retains all model and setting results, including adverse and superseded findings.

### How to read this guide

Business and policy owners can use the chapters to understand the release choices and the proposed review process. Practitioners can follow the technical companion for notation, calculations, protocol details and reproducibility. The separate experimental supplement contains all 238 experimental tables and 5,543 displayed result rows across 51 study sections; these rows are not 5,543 independent experiments.

| If you are… | Read | You will be able to |
| --- | --- | --- |
| Business or policy owner | The executive summary, main chapters and conclusion | Define a useful proposal, understand the evidence and plan a controlled pilot |
| Technical practitioner or assessor | The guide, technical companion and complete experimental supplement | Check assumptions, reproduce results and implement the supported controls |

#### Companion documents

Experimental supplement: model-risk-experimental-supplement.docx. Technical material and exact example replay: docs/publication/2026-09-28 in the AI_ModeL_Check repository. The publication manifest records the edition and file hashes.

[Open the technical companion and publication files](https://github.com/elmontu/AI_ModeL_Check/tree/main/docs/publication/2026-09-28)

## Executive summary

- Model assurance helps useful AI releases proceed with evidence and workable controls. Because trained models can retain information from their data, assess what the proposed recipient could learn from the release.

- Begin with the people and facts to protect, the access the recipient needs, and what that recipient already knows. Include anyone who could combine the covered outputs.

- Keep a shared record of earlier releases involving the same people. This makes cumulative exposure visible across recipients, projects and dataset versions, including copies retained after expiry or deletion from a current model.

- Use two kinds of evidence: attacks show exposure that has been demonstrated, while valid upper bounds show when a defined threat is within its policy limit. A successful attack can block a release if its valid lower bound exceeds that limit. Approval requires a valid upper bound for every mandatory threat; a gap in that evidence calls for further work.

- Anonymising inputs is a useful safeguard. Removing names alone can leave identifying clues and sensitive patterns, so also assess the model, its interface, recipient knowledge and earlier releases. Chapter 1 explains when anonymisation and formal privacy guarantees support the decision.

### Summary of steps

| Step | Description |
| --- | --- |
| Define the purpose and protection | State the intended benefit, the people or organisations protected and the facts that need protection. |
| Describe the access | Record what the recipient can see, query, repeat, keep and combine. |
| Understand the recipient | Include existing knowledge and everyone who could combine the covered outputs. Document any justified separation. |
| Use the right evidence | A valid attack floor above the policy limit blocks the proposal. A valid upper bound within the limit supports clearance for the threat it covers. Record unresolved cases as inconclusive. |
| Include earlier releases | Review previous and simultaneous disclosures involving the same people. Retain exported copies in the history after revocation or current-model deletion. |
| Compare useful options | Keep options that meet both usefulness and privacy requirements, then compare what they reveal. Some options may remain incomparable. |
| Record and enforce the decision | Link the approved version, computations, people and history. Reserve required allowance before computation, verify delivery and retain earlier exposure in the account. |

## 1 Why model release is a privacy decision

Public agencies, research institutes and private-sector organisations increasingly train, procure and share models built from administrative, health, education, employment, justice, financial and service-delivery data. These datasets describe real people over long periods, and they often contain information individuals cannot reasonably avoid providing, whether to receive a public service, obtain credit, get medical treatment or hold a job.

Releasing such a model, whether as an exported file, an API or access to a controlled research enclave, can transfer a new means of learning about those people, and that can cause real harm: damage to the individual concerned, breach of confidence, compromise of operational or national-security information, and loss of public trust in the services involved.

Approving a release and refusing one both need to rest on evidence. An assessment exists to let a useful release proceed, with conditions where they are needed, and to make that decision defensible either way. Several conditions make that challenging in the public sector:

| Public sector attributes | Privacy consequence |
| --- | --- |
| Large, linked administrative populations | A recipient can combine model outputs with registries, public records or agency-held identifiers. |
| Repeated releases across agencies and vendors | Models that look acceptable separately can reveal more when their outputs or structures are joined. |
| Long retention and recurring service relationships | The same person contributes to many datasets, models, checkpoints and updates over time. |
| High-impact public decisions | Disclosure of membership, identity or an attribute can affect eligibility, enforcement, stigma, safety and trust. |
| Mixed recipients and interfaces | A public API, a research partner, a contractor and another agency each have different access and different prior knowledge. |
| Statutory duties and public accountability | Government must be able to justify necessity, proportionality, evidence quality, controls and the accountable decision owner. |

### How models expose information

AI models can expose information about the people and organisations in their training, fine-tuning, retrieval and interaction data, in two ways:

- Direct exposure: The model reproduces something it saw: a memorised passage, an image, an identifier, a credential or a fragment of source code.

- Inferential exposure: The model reproduces nothing, but its outputs help the recipient work something out: whether a named person was in a dataset, which record belongs to which identity, what a hidden attribute is likely to be, or what the underlying data looked like.

How much of either a recipient gets depends on the channel:

- A downloadable checkpoint exposes every parameter and the model's internal structure.

- An unrestricted scoring API allows repeated, high-precision observations.

- A fixed label derived from the same score reveals no more than that score under the same query conditions. Repeated or adaptive queries still need assessment.

It also depends on what the recipient already holds. A weak signal becomes decisive when combined with a registry, a case file, a public record, a vendor dataset or an earlier release.

### Why anonymising training data alone is not enough

Anonymisation is useful, but saying that the training data were anonymised is not a complete model-release argument. The assessment must explain which information was removed, which identifying or sensitive patterns remain, and what the intended recipients can learn from the released model. A data-handling step and a release-specific privacy guarantee answer different questions.

Removing names is not the same as removing identifiability. Replacing names or identification numbers with persistent codes is pseudonymisation: records may still be linked through a key or other clues. Age, location, occupation, dates and unusual events can identify someone in combination, even when none identifies them alone. Effective anonymisation needs a contextual assessment of linkage and disclosure risk, including other information recipients can obtain. [A1, A2]

Models can retain information that remains in the data. A model may reproduce an unusual passage, preserve a distinctive pattern or provide signals useful for membership or attribute inference. The recipient may already know the person’s name and submit their other characteristics; the model need not output a name to help expose a protected fact. These are possibilities to assess, not claims that every model memorises or reveals every training record. The attack studies in the next section illustrate the mechanisms.

Preventing unique identification does not prevent every sensitive inference. Suppose an illustrative de-identified table leaves five people indistinguishable on the published age and location fields, and shows the same diagnosis for all five. A recipient who knows that a target belongs to that group can learn the diagnosis without finding the target’s exact row. A model may also reveal useful correlations. Any model-assisted attribute claim must be tested against an equally informed no-model baseline; an accurate prediction does not, by itself, prove memorisation or training membership.

The recipient and the release history change the assessment. A dataset transformation evaluated for one recipient may leave revealing clues for another with a registry or case records. Several model versions can expose complementary patterns that are more useful when combined. A new recipient, richer interface or additional release therefore needs assessment against the complete pooled view. Calling each input dataset anonymised does not establish a bound for that joint view. [P1–P3]

Illustrative example. An agency removes names and identification numbers from case notes but leaves a rare occupation, neighbourhood and incident date. If a released model reproduces that combination, a recipient with matching case records or a public report may link the passage to a person. The identifying information survived the removal of direct identifiers. A merely plausible generated passage would not establish that this extraction occurred.

There is an important limit to this argument. Training cannot create additional information about the source beyond the complete information it uses; it can make existing information easier to exploit. A model trained solely from one properly differentially private output, with no further access to protected data, inherits that output’s guarantee through post-processing. The guarantee keeps its original protected unit and scope, and does not prohibit all population-based inference. Raw-data fine-tuning, private selection or evaluation, retrieval from confidential records, and fresh private computations require their own valid protection and accounting. [A3]

Release decision. Treat anonymisation as one part of the evidence. Record the transformation and its assumptions, assess residual linkage and inference against realistic recipient knowledge, and bind any guarantee to the actual model, interface and complete history. Keep the least revealing useful inputs and outputs. Anonymisation can reduce exposure; the label alone cannot supply the missing ceiling for a mandatory threat.

### What the evidence shows

Published research demonstrates membership inference, training-data extraction and exposure through API fields or session logs. Reported incidents also show disclosure when confidential inputs are sent to an external service. These are different mechanisms. They justify realistic assessment but do not provide a leakage rate or a privacy guarantee for the release under review.

| Case | What was demonstrated | Key takeaways | Relevant assessment or control |
| --- | --- | --- | --- |
| Membership inference<br>Shokri et al., IEEE S&P, 2017 | Attackers used model outputs and shadow models to infer whether particular records were in a target model’s training set. | Even prediction-only access can expose participation in a sensitive government dataset. Aggregate accuracy is not the relevant privacy measure. | Test membership inference against the interface being released, not the model file alone. |
| GPT-2 training-data extraction<br>Carlini et al., USENIX Security, 2021 | Researchers recovered hundreds of verbatim training sequences by querying a released language model and ranking unusually memorised outputs. | Training on publicly sourced data does not eliminate privacy risk, and query-only access can reveal exact content. | Deduplicate training data, and run extraction tests on the model that will actually be released. |
| Diffusion-model extraction<br>Carlini et al., 2023; reported by Ars Technica | A generate-and-filter attack recovered training images, including photographs of individual people. The measured extraction rate was small and context-specific. | A low average extraction rate can still matter when a single recovered item identifies a person. Report counts, populations and uncertainty: not just rates. | Report how many individuals are identifiable, not the average extraction rate. |
| Production divergence attack<br>Nasr et al., 2023; reported by The Register | In experiments on the 2023 ChatGPT service, repeated-word prompts induced divergence and training-text extraction. The study reported a training-data emission rate about 150 times its comparison baseline. | Alignment testing and normal-behaviour testing do not establish a privacy ceiling. Adversarial use of the interface must be tested explicitly. | Include adversarial prompting in testing, not only normal-use behaviour. |
| Confidential-input incidents<br>Reported by TechCrunch and Cybersecurity Dive, 2023 | Employees reportedly entered sensitive semiconductor source code, equipment data and meeting material into a public generative-AI service. | This was input disclosure rather than proof of model memorisation, but it shows why prompts, retention, vendor use and deletion belong inside the release contract. | Set retention, vendor and prohibited-use terms before staff are given access. |
| Reasoning trace replay<br>Panfilov et al., 2026 | Researchers replayed encrypted reasoning blocks into compatible models and recovered sensitive content from publicly shared session traces. This is API and log exposure, not necessarily training-data memorisation. | Opaque fields may contain sensitive material even when the visible response has been reviewed. | Inventory returned fields, test replay and context binding, and remove opaque reasoning blocks from shared logs when their contents cannot be inspected. |

## 2 Assessing a proposed release

This chapter helps a team turn a useful idea into an assessable release proposal. It explains what to describe, how to interpret the evidence, and how to compare options. The aim is a clear next step: proceed when requirements are met, improve the proposal when they are not, or explain why the purpose cannot be supported.

### Five foundations for a useful assessment

A review becomes more useful when everyone agrees on the people to protect, the recipient’s access and the evidence needed for a decision. Start with these five foundations:

- Describe the access being offered. Record the files and services the recipient will receive, and what they can inspect, query, keep or share. The same model can create different exposure as a downloadable file and as a controlled service.

- Understand the recipient’s starting point. Include their registries, case records, public sources and earlier models, together with information other covered recipients may share. Assess the proposed release against that combined knowledge.

- Report results in context. An attack’s success rate describes a particular method, sample and amount of effort. Record those conditions, the affected population and the uncertainty so reviewers can judge what the result supports.

Look at concentrated exposure as well as averages. Report how many people are affected and examine especially revealing cases or small groups. Compare what the recipient can learn with and without the proposed release.

- Use tests to find problems and guarantees to support clearance. A test that finds no exposure is useful evidence about that test. It leaves open what a stronger attack, different recipient knowledge or another interface could reveal.

For each mandatory threat, seek a valid upper bound within the policy limit. A valid attack lower bound above that limit establishes a reason to block the proposed release. Keeping these roles separate makes both favourable and adverse decisions easier to explain.

- Review the combined history. Include models, checkpoints, reports and explanations concerning overlapping people. Recipients may learn more by combining them. Extra outputs do not improve every attack, but the recipient can always retain the information available from any one component.

The questions and examples that follow turn these foundations into a repeatable review.

### Ten questions to prepare a release request

Use these questions at intake to agree the scope and identify any information still needed. Assign an owner and next step to each unanswered question before seeking a release decision.

- What will be released, including files, outputs and observable service behaviour?

- Who will receive it, who could combine the outputs, for what purpose, and for how long?

- Whose information is protected? Does the guarantee cover a person’s recorded values, whether they appear in the data, or both?

- Which facts need protection, and which privacy threats must the review address?

- What can the recipient already learn before this release?

- Which earlier or simultaneous disclosures could recipients combine with this release?

- What minimum level of usefulness must the release provide?

- What policy limit applies to each privacy threat?

- What evidence would support clearance, and what evidence would require the proposal to change?

- Who is responsible for the decision, controls, expiry and future reviews?

| Outcome | What it means |
| --- | --- |
| Release as proposed | All mandatory requirements are met for the exact version, access and conditions assessed. |
| Release with controls | Requirements are met when specified access restrictions, monitoring, expiry or recipient controls are enforced and verified. |
| Redesign required | Change the proposed access or method, or obtain missing evidence, then reassess the revised option. |
| Reject | The declared purpose and applicable policy do not support an acceptable release option. |

These are recommendations from the assessment. A responsible authority must then approve the release, and the delivery system must check and enforce that decision. A pilot can test this separation of roles and records. The current local tools support assessment and bounded technical trials; agency approval and operational deployment require the additional arrangements described in Chapter 4 and the companion.

### What training and release can reveal

Training may retain an unusual example, a distinctive pattern or a correlation that helps infer a sensitive fact. Sometimes a model reproduces source material; sometimes its outputs help connect a pattern to a known person. The assessment checks which of these routes matters for the proposed use.

Review duplicates, rare examples and overfitting as possible warning signs. Also assess useful learned correlations: a model can predict well on new data and still help reveal sensitive information.

Match the review to the access being offered:

- A downloadable model gives the recipient its internal structure and unlimited local use, including inspection, modification and further training.

- A scoring service may return precise probabilities or internal numeric representations, which can reveal more than a decision label.

- A label-only service returns less detail per answer. Its assessment still needs to cover repeated queries and attempts to map how decisions change.

- Include supporting files and service outputs, such as logs, explanations, retrieved passages, hidden response fields and preprocessing code.

Test against realistic recipient knowledge. A recipient may know a target’s name, part of their record, their public history or their likely involvement in a programme. An agency or contractor may hold additional records lawfully. Use those circumstances when defining the test population, allowed queries and comparison baseline.

Assessment record. Agree and record the protected people, facts, recipient, prior knowledge, interface and measure of success. Review the affected evidence whenever those conditions materially change.

### Agree what needs protection

| Element | The question it must answer |
| --- | --- |
| Population | Which people or organisations does the claim cover? Specify the roster or justify the wider population and sampling approach. |
| Protected unit | Does protection apply to a person, household, company, episode, document or record? |
| Secret | Which facts need protection: participation, identity, an attribute, source content, a record link or a defined reconstruction? |
| Inclusion process | How were records included in training, tuning, retrieval or evaluation? What is known about coverage and selection? |
| Auxiliary knowledge | Which public sources, recipient records, previous models and outputs are available before this release? |
| No-release baseline | What could the same recipient work out without receiving the proposed release? |

### Describe exactly what the recipient can do

Describe the complete release: the model version, files or service access, returned fields, precision, query limits, logs and retention. For each threat, state what the recipient is trying to learn and how success will be measured. For example, a membership test must specify the rate of false alarms at which its detection rate is assessed.

- Files and versions: record a digital fingerprint (hash) and version for the model and each supporting file or configuration.

- Interface: list everything the recipient can see, query, repeat, combine or keep.

- Recipients: record access and existing knowledge for everyone who may combine the covered disclosures. Assume sharing within this group unless a narrower separation is independently justified.

- History: list the protected computations and earlier releases on which this proposal depends, across recipients, datasets and projects. Include retained versions and visible decisions covered by the assessment.

- Validity period: record the dates, policy and evidence expiry, and changes that require another review.

### Check each required privacy limit

Assess each mandatory threat against its own policy limit. A membership result and an identity-linkage result answer different questions and should remain separate. For each, record what has been demonstrated by attacks and what is covered by a valid upper bound, together with the assumptions and evidence source.

When information is missing, record an inconclusive result and the work needed to resolve it. Keep delivery on hold while required coverage, identity links, interface details or earlier releases remain unresolved. This is different from a demonstrated privacy violation or a policy rule that rules out the proposal.

### Use evidence to decide the next step

The review answers two questions:

- Has valid evidence demonstrated exposure above the agreed limit?

- Does a valid upper bound place the defined threat within that limit?

The first question identifies a demonstrated problem. The second supplies the evidence needed for clearance. A result can be inconclusive when neither question has been resolved.

#### Demonstrated exposure the floor

A floor is a lower bound on exposure supported by valid evidence. For example, an attack may demonstrate identification or membership detection above the policy limit. Use the same population, success measure and test conditions as the limit, and include the uncertainty in the result.

An attack floor above the limit is enough to block the proposed release and focus redesign on the demonstrated weakness. The true exposure may be greater than this floor.

#### Evidence for clearance the ceiling

A ceiling is a valid upper bound for a specified threat, group of people and form of access. It may come from a fully described finite experiment or a verified privacy mechanism that accounts for earlier releases. Check exactly what it protects: recorded values and participation are different requirements, and protection for one record may need conversion to cover a person’s full contribution.

A valid ceiling supports a decision beyond the attacks that happened to be tested. Within its stated assumptions, it lets the reviewer explain why the defined exposure remains within policy.

Use unsuccessful attacks as screening evidence and retain their methods and results. Then complete the approving evidence for every mandatory threat. If a ceiling is missing or insufficient, record the gap and choose a next step: strengthen the evidence, change the mechanism or narrow the interface. An upper bound above the limit alone does not demonstrate that the release violates it.

| Evidence available | Decision and next step |
| --- | --- |
| A valid attack lower bound exceeds the policy limit. | Block this proposal. Preserve the evidence and redesign the relevant model or access. |
| A valid upper bound is within the policy limit. | The threat may clear when the bound covers the actual people, recipient, interface, controls and release history. |
| No demonstrated lower bound exceeds the limit, but a sufficient upper bound is missing. | Record an inconclusive result. Obtain stronger evidence or revise the design. An upper bound above the limit alone does not demonstrate a violation. |
| An attack lower bound exceeds a claimed upper bound. | Pause the decision and investigate the conflicting evidence independently. |

Example. A ministry tests a proposed model export and finds no extractable records. It then checks whether the evidence covers the contractor’s actual access, including unlimited local queries and any rosters they hold. The ministry can seek evidence for that complete export or assess a narrower service that still meets the research need.

### Choose a useful release that reveals less

First identify options that meet the usefulness requirement and every mandatory privacy requirement. Then compare how much each option reveals. If one option can be generated from another without further protected data, under the same assumptions, it reveals no more. For example, a fixed category derived from an already available score adds no information to that score.

Apply the checks in this order:

- Usefulness: keep options whose evidence meets the minimum required performance.

- Privacy: keep options with valid approving evidence for every mandatory threat, covering the actual release and its history.

- Information disclosed: where an exact comparison is verified, set aside an option that reveals strictly more than another option that already meets both requirements.

- Choice among remaining options: apply the policy’s tie-breaks, first implementation cost and then certified usefulness.

Some options cannot be ranked by this comparison, and sometimes the evidence is insufficient to establish a relation. Record that distinction and apply the stated policy within the remaining set. Keep separate privacy threats visible rather than combining them into an unsupported overall risk score. The companion explains the formal comparison, known as Blackwell ordering.

### Privacy questions and the tests that inform them

The table separates the information to protect from the methods used to test exposure. Use attacks to investigate the relevant threat and retain the approving evidence required by the decision rule above.

| Risk | Examples of testing methods | What the attacker may learn |
| --- | --- | --- |
| Membership disclosure | Compare confidence or error on members and nonmembers; use reference models or inspect internal parameters. | Whether a specific person or record was included in training, fine-tuning or another protected dataset. |
| Memorisation and extraction | Use targeted prompts, planted test records, similarity searches or parameter inspection. | Exact or near-exact text, identifiers, images, credentials or rare training examples. |
| Attribute inference | Compare a model-assisted prediction with an equally informed method that has no model access. | A sensitive fact, such as a diagnosis, location or affiliation, that the recipient did not already know. |
| Identity linkage | Match tree routes, output patterns or numeric representations against a known list of people. | Which person, organisation or episode corresponds to a model-derived signature. |
| Reconstruction or inversion | Attempt to reconstruct source features from outputs, gradients or numeric representations. | Features or representative records resembling the protected source data. |
| Combined-release leakage | Combine observations across model versions, scores, reports, explanations and previous exports. | A secret revealed only when several individually acceptable observations are put together. |
| White-box amplification | Inspect internal parameters, trees, adapters, gradients or supporting files directly. | A more precise version of any of the above, because the exported file exposes internal structure. |

### Assess models together when recipients can combine them

Several models may give a recipient complementary clues about the same people. The combined view preserves everything available from each model, because the recipient can ignore any extra output. Whether the extra clues improve a particular attack depends on the models and recipient knowledge.

Keep a record of the computation behind each output. Sending the same fixed output again adds no observation for a recipient who already has it. Running a new randomised computation is a new source, even if its output happens to match. Assess the joint behaviour of different computations, including any shared randomness.

#### Project findings and experimental evidence

| Study and scope | Finding | Implication |
| --- | --- | --- |
| Central accounting study<br>12 synthetic settings with three matched membership realisations each [P2] | Exact ledger and graph made identical decisions. With verified disjointness, both admitted 24 of 24 proposals versus 10 of 24 for the coarse account. With complete overlap, all admitted 10 of 24. | Verified overlap avoids some conservative refusals. The benefit is not unique to graphs, and no consistent graph speed advantage was found. |
| Person-level utility study<br>64 independent worlds with two noise draws per world [P2] | A shared private source could improve on repeated fresh computation, but did not outperform the joint-workload control that knew the tasks in advance. The known-law public control was better in the displayed cases. | Compare against strong central and public-data alternatives. The evidence does not establish that protected training data were necessary. |
| Controlled deletion study<br>17 synthetic settings and 272 independent data histories [P4] | Updating sufficient statistics matched the specified retained-data ridge trainer under paired noise. Earlier exported versions remained in the history. | Removal from the current trainer and privacy of the retained history are separate. This study is record-value replacement, not person-level or participation protection. |
| Public model workloads<br>17 tree, image and language model settings | The retained runs include XGBoost, ResNet50, DenseNet121, GPT-2 and Qwen2.5-0.5B. GPT-2 holdout loss improved after fine-tuning; Qwen holdout loss worsened in all three measured sizes. Qwen membership-success lower bounds were approximately 0.82 to 0.85 in the declared benchmark. | These are model-specific attack results. Every reported privacy ceiling remained 1. The runs establish neither release clearance nor a ranking across unrelated metrics. The experimental supplement retains every setting. |
| Corrected utility study<br>28 September 2026<br>96 independent worlds across four regimes | The new unknown-teacher design includes 96 parameter cells and stronger controls. The joint-workload arm has lower mean primary MSE than zero prediction in all 96 cells; the corresponding pointwise intervals exclude zero. Fresh-full MSE exceeds zero prediction in 30 cells. | The benefit can still be small. Pointwise intervals are not a simultaneous guarantee. The full comparison and the earlier adverse results remain in the experimental supplement. |
| Finite model-history extension<br>Eight roster sizes from 1 to 40 records | At 20 records, certified joint orientation accuracy is approximately 0.993147 versus 0.967721 for optimized independent composition and 0.993789 with no retained old export. Exact verification includes numerical repair; its cost and certified gaps are reported. | The result concerns a known finite exchangeable sign-model law and record replacement. It does not establish the same improvement for arbitrary neural models. All sizes and subsequent model variants appear in the experimental supplement. |

The project results show where the proposed methods help and which comparisons matter. The 28 September utility study uses 96 independently generated worlds and stronger controls; the finite model-history study extends the checked example to 40 records. The companion preserves all settings, uncertainty, earlier adverse results and the historical follow-up that clipped predictions after initial failures. It also distinguishes independent data histories from repeated noise draws and timing runs. These are research findings within the stated study designs; operational deployment needs the pilot and approval work described in Chapters 3 and 4.

Practical check. Include the supporting assets and service behaviour in the release record: model versions, adapters, tokenisers, preprocessing, prompts, retrieval indexes, explanations, numeric representations and logs. Anything the recipient can inspect or repeat may matter to the assessment.

### Examples how the release design changes exposure

These hypothetical examples show how to reason about a proposal. Their figures illustrate the mechanisms and decision rules, rather than measured risks for Singapore residents or project performance.

#### Example 1 compare six ways to share the same model

| Candidate release | What the recipient gains | What the assessment should cover |
| --- | --- | --- |
| Complete model file | Every parameter or tree; unlimited local queries; the ability to modify the model and strip any wrappers. | Usefulness of full access, and extraction, identity linkage and unlimited-query attacks against the complete file. |
| Scoring API, six decimal places | Repeatable, high-precision outputs without direct access to parameters. | Whether precise scores give additional membership or attribute signals, including repeated queries. |
| Five-band API | Only categories, such as very low to very high. | Whether categories meet the purpose and reduce identification. A separate valid membership bound is still required. |
| Label-only API | One decision label per permitted query. | Usefulness of labels and the exposure from repeated or adaptive queries, including attempts to map the decision boundary. |
| Aggregate results | Approved group statistics rather than person-level responses. | Whether group-level results meet the purpose, with controls for small groups, subtraction of related results and repeated publication. |
| Revise the purpose or design | The purpose is revisited, or a protected model is retrained. | Choose this route when the current options cannot meet both usefulness and mandatory privacy requirements. |

#### Example 2 understand combined model fingerprints

Two government teams train separate XGBoost models on overlapping patient records. Model A predicts readmission risk; Model B predicts the likelihood of an emergency visit. Both are released to the same research partner, which already holds an authorised roster of possible patients.

For this example, assume the partner can observe a model fingerprint linked to the target and calculate comparable fingerprints for people on its roster. A fingerprint is the route a record takes through the trees. The model file by itself does not tell the partner which fingerprint belongs to the target.

- Model A alone narrows the target to 20 people who share its fingerprint.

- Model B alone narrows the target to 15 people who share its fingerprint.

- Combined, only one person belongs to both the 20-person group and the 15-person group. The overlap identifies that person.

This demonstrates identity linkage under the stated conditions. A claim about training participation or diagnosis needs separate evidence and a comparison with what the recipient could learn without the model.

| Review performed | Target narrowed to | Apparent result |
| --- | --- | --- |
| Model A by itself | 20 people sharing Model A’s fingerprint | Not individually identifying |
| Model B by itself | 15 people sharing Model B’s fingerprint | Not individually identifying |
| Models A and B combined | 1 person appearing in both groups | Person identified |

The numbers are illustrative. Identification occurs because these particular groups intersect in one person; other overlaps may leave several candidates.

Use this example to check how the actual outputs work together. Repeated or redundant fingerprints may add nothing, while complementary fingerprints can narrow the candidate group. Include the target-linked observation and the recipient’s matching records.

Decision lesson. Review every output and auxiliary record that covered recipients can combine before clearing the new release.

#### Example 3 check small groups as well as average exposure

An agency gives a research partner the complete file for an XGBoost model trained on a small service cohort. Because the partner holds the file, it can inspect the decision trees directly rather than merely submit queries. Each person’s record follows a particular route through the trees, and those routes together form a model fingerprint.

Assume the partner has an observed target fingerprint that it can match to its roster. A unique match identifies the target within that roster; a shared fingerprint leaves several candidates. This matching condition is essential: a leaf signature is not automatically an identifier for a training record.

| Observed signature group | People sharing it | Best-guess identification success |
| --- | --- | --- |
| Group A | 5 | 0.20 |
| Group B | 3 | 0.333 |
| Group C | 1 | 1.00: certain identification |

For this illustration, guessing among n equally likely candidates succeeds with probability 1/n. This is an upper bound only when the complete observation and prior information are specified and the conditional probabilities are uniform. A group’s size alone is insufficient.

Report the most revealing cases alongside the average. This helps the reviewer see whether a small group or an individual needs a different release design, particularly when the recipient has matching records.

Decision lesson. If demonstrated identification exceeds policy tolerance for a protected person, redesign the full export. Compare a controlled service, broader output bands or appropriately protected retraining against the same usefulness requirement.

#### Example 4 interpret a test with no observed false alarms

An agency plans to share an LLM fine-tuned on confidential case notes with a service vendor. Testers use names, phrases and partial passages from 3,000 people outside the fine-tuning data. They observe no false alarms. The reviewer needs to establish what this useful test result supports.

For a fixed test method and 3,000 independent, representative non-member trials, zero false alarms supports an approximate one-sided 95% upper bound of 0.1% on that method’s false-alarm rate. The calculation is in the technical companion. This result leaves open the response to other methods, recipient knowledge and repeated attempts; a broader release claim needs evidence covering those conditions.

| What was observed | What it supports | What it does not support |
| --- | --- | --- |
| No false alarms in 3,000 non-member tests | For a fixed method and independent, representative trials: an approximate one-sided 95% upper bound of 0.1% on its false-alarm rate. The exact calculation is in the technical companion. | A claim that the model contains no confidential records, or that every future attacker will fail. |

Decision lesson. Retain the counts, prompts and sampling conditions as screening evidence. Test the vendor’s realistic access and obtain the required approving evidence, or assess a narrower interface that meets the purpose.

#### Example 5 measure the contribution of the model to a sensitive inference

A government research API exposes the exact risk score from an XGBoost screening model. The recipient knows most of a person’s record but does not know whether that person has diabetes. The API lets the recipient submit a complete record and vary individual fields.

The recipient tries candidate values for the hidden field and compares the outputs with an observable target response, outcome or justified statistical reference. To show that the model helps reveal the true value, compare the attack with a baseline using the same records and existing knowledge. Different scores for two inputs alone do not establish the true value.

Illustrative result: balanced accuracy is 0.80 with model access and 0.76 for the equally informed baseline, an increase of 0.04. Evaluate both methods on the same cases, report uncertainty, and fix the selection plan and population in advance. These are invented figures used to explain the comparison.

Decision lesson. Match the controls to the tested behaviour. Options include input validation, limits on repeated changes to a person’s record, lower output precision or excluding protected input fields. Retest the exact service configuration that recipients will use.

#### Example 6 account for repeated releases

Several teams propose screening models involving overlapping people. Since covered recipients can combine the models, assess the proposed addition together with what those recipients already hold.

Membership tests may combine confidence, loss or other signals across models. The recipient retains the best information available from an individual model by ignoring other outputs. A specific test may still perform worse when combined; an improvement needs evidence.

A common privacy account can help coordinate releases concerning the same people. Each guarantee entered in it must cover the threat being assessed. The current prototype protects recorded values for a fixed population; protecting whether a person participated requires a matching mechanism and evidence. [P1–P3]

Decision lesson. Link the same people across dataset versions and project identifiers, record previous disclosures, and assess the complete recipient view. Carry earlier exposure forward when names, versions, projects or recipients change.

### Protect the whole person and account for shared access

State exactly what the guarantee protects. Record-value protection concerns changes to one fixed record. Person-value protection concerns all declared values belonging to one registered person across their fixed records and dataset versions. Participation protection concerns whether the person is included at all. A patient may need both value and participation protection; choose evidence and mechanisms that match the requirement.

For a pilot using the current central gate, the supported scope is a fixed set of registered people with fixed membership. Identity links, task definitions, certificate choices and control schedules must be set independently of protected values. A data steward must validate the identity mapping: the software relies on that mapping and cannot establish on its own that two IDs belong to the same person. [P1, P3]

Assume covered recipients may keep and share outputs. Reuse the existing charge when the same accounted private source is redelivered or processed without new protected input. Give a fresh protected computation its own execution record and charge. Distinct sources that share randomness need a valid joint guarantee; the current gate does not support that general case. The companion sets out the supported accounting conversions.

## 3 Plan a release contract and pilot

A release contract is a shared record of the proposed access, the people and facts protected, the evidence and the conditions for use. It connects the requester, reviewer and operator to the same model version and release history. In a pilot, this record helps the team test whether the assessment and controls can work together before an operational rollout. The arrangements in this chapter are proposed pilot conditions, subject to validation and institutional adoption. Existing agency requirements continue to apply.

### Use one agreed record for the release

The assurance contract describes what is being assessed and how the approved conditions will work. It records the model version, whether recipients receive files or service access, what they can observe and keep, what information needs protection, which earlier releases matter, and when access expires. Commercial and legal agreements support this record with their own duties and remedies.

| Release assurance record | Commercial or legal agreement |
| --- | --- |
| Defines the exact technical and operational release that was assessed. | Sets legal rights, duties, liability, confidentiality, licensing and remedies between parties. |
| Links the model, access, recipient, protected people, evidence, controls, earlier releases and expiry. | May impose purpose limits, security duties, audit rights, deletion obligations and incident notification. |
| Gives the reviewer and delivery operator the same precise specification to assess and enforce. | Provides enforceable duties and remedies; technical privacy evidence separately establishes whether disclosure is within tolerance. |
| Requires an updated version and review when a material technical or contextual condition changes. | Changes according to its own amendment and variation clauses. |

Use the two kinds of agreement together. For example, named-user terms and an expiry date should be supported by access controls and automatic expiry. Keep earlier copies in the privacy account: stopping future access does not undo information already received.

### What the contract helps the team do

- Make decisions accountable: show the approving officer the exact proposal, supporting evidence and assumptions.

- Make the review repeatable: let another reviewer check the same model, population, interface and policy.

- Coordinate across agencies: find earlier releases concerning the same people or protected facts before approving another.

- Turn conditions into practice: give system operators precise access, output, retention and expiry requirements.

- Manage change: identify when a new model version, recipient, output field or purpose needs review.

- Support incident response: connect affected people, recipients, files, controls and owners through the release record.

Singapore public-sector data management is governed by the Public Sector (Governance) Act and Government Instruction Manual controls. The PDPA applies to private-sector organisations, including relevant external partners. Identify the applicable authority, contractual duties and sector requirements for each release; the assurance contract does not replace them.

### Record the agreed scope and evidence

Use the fields below as the common record. Version it as the proposal develops, then fix the assessed version for the decision. A material change requires an updated release instance and a review of the affected evidence.

| Field | What to record |
| --- | --- |
| Files and versions | Digital fingerprints and versions for the model, adapters, text-processing files, prompts, retrieval index, code and supporting assets. |
| Access and outputs | Files, returned fields, precision, hidden fields, logs, query rights and retention. Include every observation and the controls required for the evidence to apply. |
| Recipients and existing knowledge | People and organisations receiving access, their purpose and capabilities, what they already know, possible sharing and any justified separation. |
| Protected people, facts and method | Authoritative person IDs and aliases, fixed dataset versions, records linked to each person, contribution limits and the exact value or participation protection required. |
| Usefulness, controls and history | Minimum performance and its evaluation; previous protected computations and releases; all sources on which the proposal depends; reuse claims and verifiable controls. |
| Policy, evidence and trusted services | Approved privacy guarantee, unique computation ID, accounting method and cost, policy limit, evidence source, randomness assumptions and the services trusted to produce results. |
| Expiry and change | Expiry of access and evidence, revocation and removal duties, review triggers and the accounting retained for delivered outputs or conservative reservations. |

### Build the record as the work progresses

Begin the contract when cross-boundary access is first proposed. Add evidence and controls as they are developed, and agree the final version before approval. The stages below are a proposed workflow for a bounded pilot. Each agency must establish the responsible roles, authority and operational controls before live delivery.

A pilot tests the process and controls; it does not create an exemption from the release requirements. Use public or appropriately approved data and controlled test outputs while developing the workflow. Any live protected release still needs the applicable evidence, authority and operational checks.

| Stage | What happens in practice | Required output |
| --- | --- | --- |
| 1. Intake | The requester states the purpose, recipient, requested model, desired interface, duration and usefulness need. | Draft request with named business and technical owners. |
| 2. Define the protected data | Register the people, project identifiers, dataset versions and records contributed by each person. State whether recorded values, participation or both need protection. | Protected population and facts, data sources and contribution mapping. |
| 3. Specify the release | Record digital fingerprints for the model and supporting files, and list outputs, precision, queries, logs and retention. | Versioned file list and service specification. |
| 4. Describe the recipient | Record existing knowledge and everything recipients can observe. Assume covered recipients can share unless a narrower separation is justified. | Recipient profile and required privacy checks. |
| 5. Check earlier releases | Identify earlier protected computations and all outputs derived from them, including retained versions and visible decisions covered by the assessment. | Complete dependency list and the latest shared-account record. |
| 6. Compare and test options | Compare useful methods and interfaces. Reserve required allowance before protected computation, including selection or evaluation when the guarantee requires it. | Recorded reservation, fixed test plan, attack results, approving bounds and usefulness evidence. |
| 7. Review and authorise | An independent assessor reviews the fixed proposal. The responsible authority records approval and updates the shared account together, so the same allowance cannot be spent twice. | Signed decision with conditions, reasons and expiry. |
| 8. Deliver and monitor | Check that the files, supporting sources and live conditions match the decision before granting access. Monitor use and enforce expiry or revocation. | Activation record, monitoring responsibilities and review triggers. |

### Assign an owner to each responsibility

| Role | Implementation responsibility |
| --- | --- |
| Requesting business owner | Owns the purpose, necessity, usefulness requirement, funding, and acceptance of operational conditions. |
| Data owner or steward | Defines the protected people and facts, verifies data sources and lawful handling, and checks contribution assumptions. |
| Model or platform owner | Records the files, versions and service behaviour; implements controls and supplies reproducible build and delivery records. |
| Independent assessor | Assesses realistic recipient access, tests options, distinguishes attack floors from approving ceilings, and records uncertainties or conflicts. |
| Privacy, legal and security reviewers | Confirm applicable authority, policy, contractual protections, security posture and unresolved obligations. |
| Authorising authority | Makes the decision within delegated authority using the required evidence and controls. Legal terms and attack results retain their distinct roles. |
| Gateway or enclave operator | Checks current authorisation, approved files and dependencies; enforces access and stops future delivery on expiry or revocation. |
| Shared registry owner | Maintains reliable links between people and a complete shared history. Coordinates reservations so competing copies cannot authorise incompatible releases. |

### Make the agreed controls verifiable

For every condition, record how it will work and how the team will check it. Distinguish controls that restrict actual access from legal or behavioural assumptions, such as a promise not to share. Where a restriction cannot be verified, include the wider access in the assessment.

| Contract condition | Insufficient on its own | Control to implement and verify |
| --- | --- | --- |
| Named recipients only | A document says access is restricted. | Individual accounts, strong authentication, role assignment and attributable logs. |
| No model export | An email tells users not to download. | Weights never enter the user workspace; enclave and network controls block file export. |
| Five-band output only | A front end rounds the score for display. | The server produces only bands; raw scores are absent from responses, logs and client-accessible errors. |
| Query limit | A usage guideline states a daily limit. | Per-user and per-subject rate enforcement, alerting and automatic suspension. |
| No onward sharing | The recipient promises not to redistribute. | Combine legal restrictions with access isolation and verifiable export controls. Include pooled access whenever sharing cannot be excluded; watermarking alone does not prevent it. |
| 90-day expiry | A calendar reminder asks someone to close access. | Automatically expire credentials and service access. Record what deletion was verified, and keep any earlier retained observations in the privacy account. |
| Approved version only | A deployment ticket lists a model name. | Check digital fingerprints of the approved files and configuration before activation and after restart. |

### Plan for change and expiry

Agree the review triggers and responsible operator before access starts. If a trigger occurs, the service should stop or route the case for review as specified. A minor change may need only an assessment of affected fields when it is demonstrably no more informative; a material change needs a new release assessment.

| Trigger | Required response |
| --- | --- |
| New model, checkpoint, adapter, tokeniser, prompt package or retrieval index | Register the new files and versions, then review the affected privacy, usefulness, safety and security evidence. |
| More precise outputs, new fields, higher query limits, explanations or downloadable weights | Assess the additional information and access before enabling the revised interface. |
| New recipient, subcontractor, user group, location or onward-sharing route | Review capabilities, possible sharing and existing knowledge, and confirm authority. Carry earlier exposure forward in the shared account. |
| Any new release concerning the same population or secret | Update the common account and combined history before the new protected computation or release. |
| Purpose expansion or secondary use | Submit a new request with a purpose, necessity and usefulness case for the proposed use. |
| Evidence, policy or authorisation expiry | Suspend access unless a renewed decision is committed before expiry. |
| Leakage incident, control bypass or a materially stronger attack becoming known | Suspend or restrict access, preserve logs, investigate impact, and reassess all affected releases. |

### Start with a bounded pilot

- Use one intake form with a unique release ID and named business and technical owners.

- Keep a structured list of model files, versions, digital fingerprints and service behaviour.

- Maintain one authoritative record linking protected people, dataset versions, protected computations and releases, including reused sources.

- Store the evidence, assumptions, policy version and reviewer decisions in a protected, traceable record.

- Separate the requester, independent assessor and decision authority in proportion to the release risk.

- Use one controlled delivery path that checks the authorised version and conditions before granting access.

- Link monitoring, incident response, expiry and removal checks to the release ID, while preserving the accounting for earlier disclosures.

Pilot scope. Begin with a defined group of people, a small set of approved mechanisms and one authoritative release path. Include all relevant recipients and earlier releases even when the pilot itself is small. Use an exact ledger to track the account and a dependency view to explain how outputs relate. The completed comparison supports overlap-aware accounting; it found no general graph speed advantage. Validate that the records cover actual exports before expanding the pilot. [P1–P3]

### A useful planning release that clears

This is a deliberately simple synthetic example. Its results are calculated exactly from a stated mathematical model; they are not measurements from an agency or a project deployment. It shows how a release can pass every specified check with room to spare. The accompanying technical note and executable verifier supply the complete construction.

The purpose. A planning team needs a high-or-low forecast of next month's overall service demand to choose a staffing level. It does not need individual predictions. The candidate is a tiny model with one learned binary output: every permitted request returns the same stored forecast. The source contains at most one binary contribution per person. Eligibility is public, but actual participation and individual values are protected.

The design. An approved randomized count mechanism chooses the forecast once. Adding, removing or changing one person's contribution changes the probability of either output by at most a factor of 1.01. This protects participation as well as values in this example; it is a different guarantee from a mechanism that assumes participation is fixed. Individual records, counts, scores and person-level responses are never delivered.

The whole history. An earlier planning team already received this exact stored forecast. The new team receives the same bytes, with no new access to the source and no fresh random draw. Even if the teams pool everything, their combined observation is still one forecast. The registry retains the original computation and its charge; the second delivery refers to that same source.

The evidence. The synthetic demand pattern is strong enough that the forecast is useful despite the protection of each contribution. Its expected accuracy exceeds 89.99%, compared with a 75% requirement; before the original protected computation, the best forecast scored 50%. This is exact expected performance under the example's known demand law, not a measured confidence interval for a fitted model. The attribute calculation compares the same background information under either value of a person's secret. For identity, the stipulated recipient information leaves 100 equally likely candidates; assigning the same records to different candidates leaves the released count mechanism unchanged.

| Check | Example's limit | Calculated result | Status |
| --- | --- | --- | --- |
| Membership | Detection at most 1%, at false-positive rate at most 0.1% | Detection at most 0.101% for the complete history | Clear |
| Identity | Correct identification at most 5% | 1% in the specified 100-candidate game | Clear |
| Attribute | Increase in binary inference success at most 2 percentage points | Increase at most 0.25 percentage points | Clear |
| Usefulness | Expected planning accuracy at least 75% | Expected accuracy greater than 89.99% | Pass |

Decision. Approve this candidate for the next month’s staffing decision within the stipulated example. Every mandatory privacy check clears and the usefulness margin is substantial. The accountable authority binds the model, source, complete history and permitted interface; the gateway delivers only the stored forecast. A later retraining or independently randomized answer needs a new assessment. Different auxiliary information also requires reassessment of the identity and attribute games. The successful result comes from releasing information that serves the planning task while limiting what one person's contribution can change.

### A useful release awaiting attribute evidence

This illustrative readmission project seeks a useful research model. The initial model-file export reveals too much in the specified identity and membership tests. The team compares controlled alternatives and finds that a privacy-trained five-band interface can meet the usefulness target. After including the earlier release, it also meets the stated membership and finite identity limits.

The remaining question is whether the recipient could infer the protected health attribute beyond the agreed limit. The example has no valid bound for that threat, so the recommendation remains on hold. The next task is specific: establish that bound or redesign the output. The full calculations and assumptions are in the technical companion. This outcome shows how the assessment narrows the work needed for a decision.

### Agree the conditions of use

- State the permitted purpose, protected population and approved environment.

- Give access to named roles through individual credentials and attributable logs.

- Specify and enforce the permitted outputs, query and export limits, monitoring and suspension process.

- Require review before any onward release, sublicensing, public upload, derived checkpoint publication or new combination of releases.

- Provide a clear route and responsible contact for reporting suspected extraction, sensitive inference, credential exposure or control bypass.

- Record expiry, return or verified-deletion duties and the model, data, interface, recipient, purpose or policy changes that trigger reassessment.

### Conditions that support a defensible approval

| Approval condition | Why it matters |
| --- | --- |
| Approve a specific release. | Identify the model and configuration by digital fingerprint, together with the recipient, interface, purpose and validity period. |
| Keep legal duties and privacy evidence distinct. | Licences, confidentiality terms and supplier commitments allocate duties. A valid upper bound supplies the technical evidence for the covered privacy threat. |
| Choose useful access that reveals less. | Where a controlled interface meets both usefulness and privacy requirements and is verified to reveal less, prefer it to a full export. |
| Use the required evidence for each threat. | Retain attack tests and their uncertainty. Support clearance with a valid upper bound covering realistic recipient access and knowledge. |
| Include the complete release history. | Earlier models, scores, explanations and recipient-held information may provide complementary clues. |
| Assess every returned field. | Encrypted, hidden or internal fields may carry sensitive material or credentials. Include them in the interface record and tests. |
| Verify the controls relied on by the decision. | Check restrictions in the deployed service. Record promises and other unverified conditions as assumptions. |
| Review changes and renewals explicitly. | A material change or expiry calls for a recorded reassessment and decision before the new access begins. |

Contract check. Compare the record with what recipients can actually download, query, keep, combine or inspect, including fields absent from the visible screen. Approval should cover that complete access.

## 4 Govern the pilot and define its scope

Governance gives a useful pilot clear ownership, review standards and a controlled route to a decision. Start with a system record, an accountable owner and a proportionate risk classification. Include the full service: data flows, models, prompts, retrieved material, tools, people and suppliers. The roles and workflow below are proposals for the validation pilot, rather than an adopted whole-of-government release policy.

### Give the team clear decision rights

Agree who can propose, review, approve, operate, suspend and retire the release. Use independent challenge in proportion to risk and keep the operator’s responsibilities clear. This helps an approved release stay within its purpose and conditions as the service changes.

Define scope around the service and the recipient’s access. Include preparation, model use, supporting services, recipient-held information and earlier releases wherever they affect observations or outcomes for people. The four levels below help the team make that boundary explicit.

| Scope level | Question to answer | Example |
| --- | --- | --- |
| Service scope | What public function, decision or workflow uses the AI, and who can be affected? | A benefits-triage service includes intake data, model scoring, officer review, notice and appeal: not only the classifier. |
| Technical scope | Which models, prompts, retrieval sources, tools, APIs, logs and hosting environments form the service? | An LLM assistant includes its system prompt, vector store, document parser, tool credentials and moderation layer. |
| Release scope | What exact artefact and interface will a named recipient receive and retain? | A five-band XGBoost API with daily limits is a different release from downloadable weights or six-decimal scores. |
| Combined release scope | What previous outputs can recipients combine across people, projects and dataset versions? | Assess a new model with earlier checkpoints, reports and outputs available to any covered recipient. |

### Agree responsibilities before testing

Assign the decision roles and evidence standards before testing starts. This gives requesters a predictable route to approval and gives reviewers a stable basis for judging the results.

| Decision | Accountable role | Review safeguard |
| --- | --- | --- |
| Accept the purpose and usefulness need | Business or service owner | Evidence standards are set through the agreed governance process, independently of the requester’s preferred outcome. |
| Define the protected population and secrets | Authoritative data owner or steward | Use reliable sources and document uncertainty or changes in the population. |
| Produce the release and its controls | Engineering or platform owner | Use independent approval of higher-risk evidence produced by the engineering team. |
| Assess privacy and other mandatory threats | Independent model-assurance function | Provide access to the actual model, interface, recipient assumptions and release history. |
| Confirm legal, privacy and security obligations | Relevant control functions | Record open conditions and the evidence or action required to resolve them. |
| Authorise residual risk | Named authorising authority | Assign authority outside the submitting team, within an explicit delegation. |
| Activate, suspend and expire access | Gateway or enclave operator | Verify the authoritative decision and approved configuration before activation. |

### Use a staged governance workflow

- Register the use case: record the public purpose, intended users, affected people, proposed access and accountable owner.

- Set the review level: consider sensitive data, high-impact decisions, vulnerable groups, external recipients, automated actions and open access.

- Agree the assessment plan: set mandatory threats, policy limits, evidence standards, reviewers and decision authority before collecting results.

- Review the complete proposal: bring together data, model, interface, recipient, earlier releases, controls, usefulness and operational readiness.

- Record the decision: state the outcome, conditions, reasons, owners, expiry and any unresolved or dissenting findings.

- Activate and monitor: deliver the approved version, check the conditions, and suspend or reassess access when an agreed trigger occurs.

Use review that is independent of the submitting team, with stronger separation and authority for more sensitive data, broader access or greater potential harm. The business owner’s benefit case and the assessor’s evidence review are both needed.

### Agree pilot success criteria before expanding

Define the use case, participating teams, protected population, supported methods and delivery path. Set criteria for usefulness, complete records, independent review, correct accounting, enforced access and incident response. A successful pilot demonstrates these within its stated scope; wider adoption requires a fresh decision on the additional people, access and controls.

### Keep a concise system record

- Purpose, users, affected people and prohibited uses.

- Model, provider, version, hosting arrangement and major components.

- Training, fine-tuning, evaluation, prompt and retrieval data categories.

- Inputs, outputs, integrations, automated actions and human review points.

- Decision impact, number and location of affected people, accessibility needs and foreseeable misuse.

- Named owners for business, technical, privacy, security, safety and incident response.

### Choose the level of review

| Signal for stronger review | Additional review or control |
| --- | --- |
| Safety-critical or rights-impacting decision | Independent review; validated human oversight; stronger release authority. |
| Sensitive or large-scale personal data | Privacy impact assessment; minimisation; strict access and retention controls. |
| Autonomous action or external tool use | Limit permissions and transaction scope; add confirmation, rollback and an emergency stop. |
| Public-facing generative AI | Misuse testing; content safeguards; disclosure; abuse monitoring and an appeal route. |
| Foundation-model or vendor dependency | Supplier evidence; contract controls; version-change notification; fallback plan. |

### Outputs to expect from the pilot

- A unique system and release ID linked to the responsible business, data, technical and control owners.

- A map of data flows, models, interfaces, recipients, suppliers and human decisions.

- A reasoned risk classification, required reviews, evidence standards and decision authority.

- A release contract and evidence package linked to exact versions and the shared release record.

- A signed decision with verifiable conditions, monitoring signals, expiry, reassessment triggers and documented exceptions permitted by policy.

- A tested incident process that can identify and suspend affected releases promptly.

### Example scope for a research release across agencies

Agency A proposes sharing an XGBoost model trained on linked administrative records with a social-policy research unit in Agency B. The team begins by documenting the proposed internal transfer and research purpose.

The intake review identifies three relevant facts: Agency B holds an authorised household roster, the export includes the complete trees, and the same unit received an earlier checkpoint six months ago.

The team includes these facts in an independent privacy and release-history review. The data steward links the protected people or households across agencies and checks their contributions. Engineering records the actual computations and model files. The assessor includes the roster, earlier checkpoint and other outputs covered recipients may share. The responsible authority and delivery operator retain their separate approval and activation roles.

Outcome. Early scoping gives the team a complete and relevant test plan. It can now compare the full export with more limited access against the same research need, and explain what evidence and controls would support a decision.

### Use the pilot to test a shared privacy account

A shared privacy account can coordinate releases without moving every raw dataset into one place. It needs reliable links between people, a complete record of covered exports and an authoritative way to update the account. This allows agencies to see the effect of a proposed release on the same people’s cumulative exposure.

The local prototype demonstrates part of this process: it reserves allowance before a protected computation and checks the recorded outputs and dependencies before delivery. Conservative reservations remain charged after failure or abandonment; earlier disclosures remain charged after revocation. Its delivery support is limited to bundles of approved source outputs. The companion describes the technical boundary. [P3]

Before an operational pilot, independently check the identity mapping, approved producers, storage, account authority and export controls. Deployment must also validate the actual privacy mechanism, including any Gaussian sampling implementation. The current prototypes and abstract proofs do not supply these agency-wide controls automatically. Use the pilot to demonstrate them before widening the release path. [P1–P3]

## 5 Building privacy in from the start

Privacy is easier to manage when the purpose, inputs and access are designed together. Map the personal information used by the service and keep only what the purpose needs. Check identifiers and sensitive patterns in prompts, numeric representations and coded records as carefully as in the source data.

### What privacy by design means for models

Privacy by design reduces exposure while the data, training method and service interface can still change. Identify whose information the model uses, what facts need protection, who can access the service and what they already know. Chapter 1 explains why removing direct identifiers is one useful step within this wider assessment.

Compare ways to meet the same need with less protected information: omit unnecessary inputs, use public data where sufficient, offer controlled access or use an appropriately private training method. Check each design against both usefulness and the required privacy evidence. Rounding, regularisation, deletion and dependency records have useful roles, but none alone establishes every required guarantee.

| Lifecycle point | Privacy design question | Practical implementation |
| --- | --- | --- |
| Purpose and collection | Which data are necessary for the declared public function? | Keep the fields and history needed for the purpose. Justify any sensitive or free-text input against the agreed usefulness measure. |
| Preparation | Can identifiers, rare values or repeated contributions make a person distinctive? | Separate direct identifiers, limit contributions, review rare combinations and preserve reliable links to the protected person or unit. |
| Training and tuning | Could records be memorised or over-represented across repeated runs? | Limit each person’s full contribution, record training and tuning access, and account for protected computations that influence covered outputs or decisions. |
| Retrieval and prompts | Can confidential material enter context, traces or vendor systems? | Use approved sources, apply access filters before retrieval, minimise prompt content, exclude secondary training and limit retention. |
| Release interface | Does the recipient actually need weights, precise scores, explanations or unlimited queries? | Choose among useful, privacy-feasible access options using verified information comparisons. Enforce precision, fields, query limits, export and expiry on the server. |
| Operation and deletion | Where do prompts, outputs, embeddings, logs and copies persist? | Apply retention and access controls. Verify the specified removal from the current training result and continue accounting for earlier recipient-held versions. |

### Build privacy into six practical steps

- Map the data: trace training, tuning, evaluation, retrieval, prompts, outputs and logs from collection through retention and deletion.

- Define protection: identify the person, household, company, episode or document covered, and the facts that need protection.

- Minimise contributions: remove unnecessary content and limit how much one protected person or unit can contribute across records and datasets.

- Compare access options: test model files, controlled services, output bands, labels, aggregates and private training against the same usefulness requirement.

- Test realistic access: include recipient knowledge, queries and earlier releases. Keep demonstrated attack results distinct from approving upper bounds.

- Plan retention and rights processes: implement the access, correction, deletion, review and incident procedures that apply. Record what is removed from systems, what changes in the current model and what earlier recipients may still hold.

### Match each control to a privacy question

| Threat | Preventive design choices | Evidence to collect |
| --- | --- | --- |
| Memorisation and extraction | Remove duplicates and secrets; restrict free text; control capacity and checkpoints; use protected training where appropriate. | Targeted extraction, canary and rare-sequence tests, run against the actual release interface. |
| Membership inference | Reduce overfitting; bound contributions; restrict precise confidence outputs; limit repeated queries; account for all related releases. | Test membership at the agreed false-alarm rate and obtain a valid upper bound for clearance. |
| Attribute inference | Exclude unnecessary sensitive fields; prevent modified-field probing; reduce output precision; restrict recipient auxiliary data and purpose. | Evaluate the model-assisted and equally informed no-model methods on the same cases, with uncertainty. Separately obtain the upper bound needed for clearance. |
| Identity linkage | Avoid exporting revealing structure or embeddings; group outputs; protect small cells and unique patterns. | Check average and most revealing cases using the recipient’s real candidate list and matching information. |
| Cross-user or cross-tenant disclosure | Filter retrieval by authorisation before the model sees anything; isolate tenants, memory, caches and tools. | Test permitted and denied access, adversarial sessions and logs across user boundaries. |
| Hidden-trace or credential leakage | Minimise internal traces, scan prompts and outputs, and keep credentials outside model context with limited tool permissions. | Scan for secrets, test whether fields can be replayed, and inspect visible and hidden responses end to end. |

### Choose a method that fits the purpose

Different methods help at different points in the service. Use the table to match each method to the purpose and required usefulness, then check the conditions on which its protection depends.

| Method | Useful when | What to verify |
| --- | --- | --- |
| Data minimisation and aggregation | The purpose does not require person-level detail or full history. | Check small groups, differences between related statistics and the combined effect of repeated publication. |
| Pseudonymisation or tokenisation | Direct identifiers are unnecessary in normal processing, but controlled linkage is still required. | Check linkage through keys or combinations of attributes. Removing names is useful but does not alone establish effective anonymisation or model-release clearance; see Chapter 1. |
| Differentially private training | A valid accountant can cover the complete pipeline, and utility remains sufficient. | Define which record, person, value or participation change is protected. Verify contribution limits, randomness and accounting for all covered training, selection, tuning and evaluation. Use the technical companion for the conversions. |
| Synthetic data | Testing or development can proceed without direct use of production records. | Evaluate similarity to source records and membership inference. A synthetic label alone is not a privacy guarantee. |
| Secure enclave or controlled API | The recipient can achieve the purpose without possessing the weights or the raw data. | Verify permitted outputs, logs, administrator access and export paths in the actual environment. |
| Secure computation or federated methods | Data must remain with separate custodians while a bounded computation is performed. | Assess the information revealed by outputs and updates, and document the trusted parties and implementation assumptions. |

### Put the supporting controls in place

- Purpose and authority: document why each data category is needed, the applicable authority and the permitted uses.

- Data minimisation: remove unnecessary fields, histories, identifiers and free-text content before collection or model access.

- Transparency: explain AI involvement, data sources, retention, significant effects, available choices, and routes for questions or challenge.

- Rights and review: implement the access, deletion, correction and challenge processes that apply to the service and its governing regime, including relevant vendor-held data.

- Retention and deletion: specify removal from source systems, search indexes, caches and backups, together with any required model update. Record what was verified and preserve the account for earlier exports.

- Access and isolation: give users and tools only the access they need, separate user environments and protect credentials.

- Locations and suppliers: record processing locations, subcontractors, contractual duties and relevant government-access risks.

- Privacy-enhancing methods: consider aggregation, de-identification, differential privacy, secure computation or synthetic data where appropriate.

Generative AI inputs. Give users clear guidance on permitted uploads and prompts. By default, exclude supplier training and secondary use, use short justified retention, and restrict retrieval to approved sources and permissions.

### Retain evidence that another reviewer can check

| Test | Evidence to retain |
| --- | --- |
| Data leakage and prompt extraction | Prompts, responses, counts and rates, affected population, uncertainty, severity and mitigation retest. |
| Membership inference and memorisation | Method, sampled records, thresholds, false-alarm operating point, counts, uncertainty and results. |
| Cross-user or cross-tenant exposure | Permitted and denied access cases, authorisation logs and results across user boundaries. |
| Sensitive attribute inference | Protected attribute, recipient knowledge, equally informed no-model method, shared evaluation cases, uncertainty and the pre-agreed selection plan. |
| Deletion effectiveness | Source and downstream removal evidence, named reference trainer on retained data, update comparison, usefulness and retained release history. |

### Example design for a case note drafting assistant

A service team wants an LLM to help officers draft case summaries. Its initial proposal sends complete files, including names, contact details, third-party information and older free text, to a hosted model. The supplier retains prompts and outputs for 30 days and may use them for service improvement. Officers can paste any text, and the case system stores drafts and internal reasoning traces.

The design review identifies a narrower route to the same drafting purpose. The model receives approved current fields after direct identifiers and unrelated third-party passages are removed. Retrieval follows each officer’s existing case permissions. Supplier secondary training is disabled through contractual and technical controls, retention is shortened, and internal reasoning traces are neither requested nor stored. Credentials stay outside model context, and an officer reviews the draft before it becomes an official record.

| Design issue | Initial proposal | Design chosen for review |
| --- | --- | --- |
| Input scope | Entire case file, plus unrestricted officer pasting. | Approved minimum fields; identifiers and unrelated third-party text removed. |
| Retrieval | The model can retrieve broadly from the case repository. | Authorisation filter applied before retrieval; only records the current officer may access. |
| Supplier use | Prompts may be used to improve the supplier’s service. | No secondary training and no human review; processing location and subprocessors documented. |
| Retention | Prompts and outputs retained for 30 days. | Shortest operational retention; deletion verified across logs and vendor systems. |
| Hidden data | Reasoning traces stored alongside the draft. | Hidden traces not returned, retained or published; visible fields scanned for secrets and personal information. |
| Official action | The draft may be copied straight into the record. | A named officer verifies accuracy, necessity and third-party disclosure before adoption. |

Verify the redesigned service through tests of prompt extraction, cross-case retrieval, indirect prompt injection, secret recovery and deletion. Run them against the actual service configuration. Record the results alongside the required approving evidence; any remaining gap has an owner and a next step before authorisation.

Design outcome. The team preserves the drafting purpose while reducing the protected information the model receives, limiting access to relevant cases and removing unnecessary traces. The resulting controls are concrete enough to test, monitor and include in the release decision.

### Check readiness for the release review

☐ The purpose, lawful authority and permitted uses are documented for each personal-data flow.

☐ The protected people, facts and contribution limits are defined using reliable records.

☐ Unnecessary identifiers, rare fields, histories, free text and duplicates have been removed or justified.

☐ The chosen option meets both usefulness and privacy requirements and is among the least informative options supported by the verified comparisons.

☐ Tests include realistic recipient knowledge, query rights, possible sharing and relevant earlier releases.

☐ Applicable retention, deletion, access, correction, objection, appeal and incident processes work across internal and supplier systems.

☐ Each mandatory threat has valid evidence covering the actual release. Any missing or insufficient upper bound has a documented next step, with delivery held until the requirement is met.

### Check whether an existing private source or public data can meet the need

Before commissioning repeated training, compare reusing an appropriately private result, planning the tasks together and using public information. In the earlier person-level study, reuse avoided redundant private computation. A joint mechanism with advance knowledge of the tasks performed at least as well, and a public control that knew the generating law performed better in the displayed cases. These strong controls show why a team should demonstrate the value of protected data for its particular task. The companion preserves the study assumptions and the later corrected comparisons. [P2]

Record what each alternative is allowed to know. Planning tasks jointly assumes those tasks are known in advance. Reuse can only process information already in the private source; new labels or protected inputs may require a fresh charged computation. Task selection and other choices based on protected data also need to be covered by the privacy argument.

### Plan deletion and future access together

Check three outcomes separately: whether the specified information has been removed from the current training result, how useful the replacement remains, and what earlier recipients may still learn from retained versions. A dependency record helps locate affected outputs and organise these checks.

The controlled ridge study supports one specific removal method. It subtracts the deleted records’ contributions from exact summary statistics and compares the update with retraining on retained data using paired noise. The study covers 17 settings and 272 independent synthetic data histories. Its protection concerns changes to fixed records on public rosters; separate evidence is needed for person-level or participation protection, private deletion schedules and language-model unlearning. [P4]

In that study, more replacement releases at the same final sample size and lifetime allowance increased the distance between private and reference predictions. Fresh-seed confirmation reproduced the specified descriptive trends. This distance is different from error against true labels. For new computations, use appropriately accounted randomness: sharing additive noise between different aggregates can allow their difference to reveal a deleted contribution.

Use revocation to stop future controlled delivery and deletion to meet a stated removal specification. Continue accounting for information already disclosed, even when the model or dataset receives a new name. This gives the replacement model a clear, reviewable starting point.

## Conclusion

A well-scoped assessment gives teams a practical route to useful model sharing. Start with the intended benefit, the people and facts to protect, and the recipient’s actual access. Compare designs that meet the purpose, taking account of existing knowledge and earlier releases.

Use attack evidence to identify demonstrated problems and valid upper bounds to support clearance. Keep each mandatory threat visible. Link the chosen model, protected computations, release history and conditions to the responsible reviewer, decision authority and operator.

For Singapore’s public sector, this approach can support useful AI services while making decisions easier to explain and audit. It complements the applicable legal authority, Government Instruction Manuals, procurement, security and sector requirements. A bounded pilot provides a manageable way to test the records, responsibilities and controls before wider adoption.

### Five principles for a useful pilot

- Define the people and facts to protect, together with the public purpose.

- Assess what recipients can learn from the complete set of outputs and information they may combine.

- Use valid attack floors to identify excessive exposure and valid upper bounds to clear each mandatory threat.

- Choose among useful, privacy-feasible options using verified comparisons of what they reveal, and enforce the chosen conditions.

- Keep decisions traceable, review material changes and carry earlier disclosure forward after expiry, revocation or deletion.

Start with one bounded use case, one authoritative release path and clear owners. Define the evidence and controls needed for approval, test them, and record both progress and remaining gaps. The guide provides the decision pathway; the technical and experimental companion supplies the calculations, implementation boundaries and full research record for independent review.

## Appendix A Assurance record

Use this as a compact index to the complete evidence package. The supporting population mapping, computation history, certificates and review records may require separate attachments.

| Field | What to record |
| --- | --- |
| Artefact / interface / recipient | Hashes and versions; every observation the recipient can make; recipient identity, purpose and access. |
| Population / protected unit / secret | Canonical people and aliases, dataset versions, contribution mapping, protected secrets and the precise value or participation protection definition. |
| Prior knowledge / history | Public and recipient-held knowledge, pooled recipients, all covered retained versions and visible decisions, and the current common-account revision. |
| Mechanism / utility | Approved mechanism and accounting family, actual execution IDs and dependencies, protected-unit cost, utility floor and strongest permitted comparison controls. |
| Threat evidence / tolerances | For each required threat, record its agreed limit, demonstrated exposure, valid upper bound and the source of each piece of evidence. |
| Controls / trust profile | Technical, contractual and operational controls, and which of them are assumptions rather than enforceable. |
| Open findings | Severity, owner, mitigation, due date, and the evidence needed to clear each one. |
| Monitoring / expiry | Stop triggers, evidence and access expiry, trainer-relative removal checks and retention of prior disclosure charges. |
| Decision | Release / release with controls / redesign / reject: with approvers and date. |

### Release checklist

☐ Intended, prohibited and out-of-scope uses are explicit and have been communicated.

☐ Data flows, lawful basis, minimisation, retention, access and rights processes are approved.

☐ The threat model and abuse cases cover the deployed architecture and its integrations.

☐ The evaluation plan, datasets, thresholds, results, limitations and retests are versioned.

☐ Human oversight, user notice, recourse and accessibility have been tested with representative users.

☐ Vendor controls, service terms, locations, subprocessors and change notifications are acceptable.

☐ Monitoring signals, owners, alert thresholds, rollback, kill switch and incident playbook are operational.

☐ Residual risks, exceptions, expiry dates and authorised sign-offs are recorded.

### Evidence to retain for the pilot

| Artefact | Owner | Refresh trigger |
| --- | --- | --- |
| System or model card | Product and engineering | Material model, prompt, data or use change |
| AI impact and privacy assessment | Risk and privacy | New purpose, data, population, geography or law |
| Threat model and security test report | Security | Architecture, tool, vendor or threat change |
| Evaluation and red-team report | Model assurance | New version, drift, incident or threshold change |
| Human oversight and user research record | Product and UX | Workflow or affected-user change |
| Release decision and risk acceptance | Accountable owner | Each release, or expiry of an exception |

## Appendix B How the proposed approval process works

The pilot would separate four decisions so that readers can see who assessed the evidence, who accepted the proposed use, and who enabled access. A favourable research result is one input to that process.

| Stage | Purpose |
| --- | --- |
| Assess the evidence | Check usefulness, every required privacy threat, assumptions and the complete release history. Record clear, blocked or inconclusive results. |
| Make the institutional decision | The responsible authority considers the evidence, applicable obligations and operational conditions, and records the scope and duration of any approval. |
| Record the decision and allowance together | Update the authoritative release record and shared privacy account together, preventing two requests from relying on the same unspent allowance. |
| Activate and monitor | Verify the actual files, interface and conditions before access starts. Suspend access when the agreed conditions cease to hold. |

Current status. MRA alpha 0.8.0 offers local assessment tools. Separate research prototypes test bounded export and accounting operations. The Lean proofs cover an abstract protocol; they do not verify the Python software, cryptography, identity service or production deployment. The technical companion records the detailed lifecycle, conformance levels, proof boundaries and verification artefacts.

## Appendix C Glossary

Plain-language definitions of the main terms used in this guide and its companion material. Related terms are grouped together.

### What is being protected

| Term | Plain-language meaning |
| --- | --- |
| Protected unit | The thing privacy attaches to: usually a person, but it may be a household, a company, a case episode or a document. |
| Population | The defined group of protected units that a privacy claim covers. A claim about "patients in this snapshot" is not a claim about all patients. |
| Secret | The specific fact the release must not reveal: whether someone was in the data, who a record belongs to, a sensitive attribute, or the content of a record. |
| Contribution bound (g) | The maximum number of records, episodes or documents that one protected unit can contribute. If one patient can appear three times, g = 3. |
| Auxiliary knowledge | Information available before the proposed release, including public records and all covered recipients’ pooled data, old models and outputs. |
| No-release baseline | What the recipient could already work out today, without the new release. New exposure is measured against this, not against zero. |
| Person value replacement | Changing all declared protected values of one registered person while membership and row structure remain fixed. |
| Participation protection | Protecting whether a person is included; it requires a matching adjacency definition, mechanism and metadata treatment. |

### How models leak

| Term | Plain-language meaning |
| --- | --- |
| Membership inference | Working out whether a specific person’s record was used to train the model. |
| Attribute inference | Working out a sensitive fact about someone that the recipient did not already know, such as a diagnosis. |
| Identity linkage | Matching a pattern produced by the model to a specific named person on a list the recipient holds. |
| Extraction / memorisation | Getting the model to reproduce something close to an actual training example: text, an image, an identifier or a credential. |
| Reconstruction / inversion | Rebuilding features or approximate records from model outputs, gradients or embeddings. |
| Leaf signature (fingerprint) | In a tree-based model such as XGBoost, the specific combination of branches a record follows. Rare combinations can belong to one person. |
| Shadow model | A model an attacker trains themselves to learn what a target model’s outputs look like for data it did and did not see. |
| Canary | A deliberately planted, unique record used during testing to check whether the model memorises and can be made to repeat it. |

### How models are released

| Term | Plain-language meaning |
| --- | --- |
| Artefact | The actual files being released: the model, plus adapters, tokenisers, prompts, indexes and preprocessing code. |
| Checkpoint | A saved copy of a model at one point in training. Several checkpoints of the same model are several releases. |
| White-box vs black-box | White-box means the recipient holds the file and can look inside. Black-box means they can only ask questions through an interface. |
| Score API / label-only API | A scoring interface returns a number, such as a probability. A label-only interface returns just a decision, which reveals less. |
| Banding | Replacing a precise score with a category: for example five bands from very low to very high. |
| Embedding | A numeric representation of a record or a piece of text. Embeddings often carry more identifying signal than people expect. |
| Enclave | A controlled computing environment where a recipient can use a model without being able to copy it out. |
| Release contract | The frozen written description of exactly what is being released, to whom, through what interface, with what controls and for how long. |
| Portfolio | All covered retained models, outputs and visible decisions across recipients, projects and dataset versions, assessed as a joint observation history. |
| Certified source execution | One actual approved randomized computation with immutable identity and output. Rerunning it is a new source. |
| Dependency closure | All upstream certified computations needed to account for a release, including reused sources. |

### Evidence and thresholds

| Term | Plain-language meaning |
| --- | --- |
| Floor (L) | Exposure that has actually been demonstrated. A floor above tolerance blocks a release. The true exposure may be higher. |
| Ceiling (U) | A valid upper bound for one defined threat and channel. It supports clearance only within its protection scope and while its assumptions hold. |
| Tolerance (τ, tau) | The maximum exposure that policy permits for one threat, at one stated operating point. |
| Operating point | The specific setting at which a result is measured: most often, how many false alarms the attacker is willing to accept. |
| False-positive rate (false alarm) | How often the attacker wrongly claims a match. Privacy results at a high false-alarm rate are usually not policy-relevant. |
| True-positive rate (catch rate) | How often the attacker is right when the answer really is yes. |
| Confidence bound | A statistical bound at a declared confidence level. The full decision must also account for selection and multiple bounds; one interval is not a universal privacy ceiling. |
| Rule of three | With zero observed events in n independent, representative trials of a fixed method, 3/n is an approximate one-sided 95% upper bound on that method’s event rate. |
| Utility floor | The minimum usefulness the release must retain to be worth making at all. |
| Balanced accuracy | An accuracy measure that treats both classes equally, so it is not inflated by a rare outcome. |

### Privacy techniques and formal tools

| Term | Plain-language meaning |
| --- | --- |
| Differential privacy | A guarantee limiting how output distributions change between explicitly defined neighbouring datasets. Its meaning depends on which person, record, value or participation change is protected. |
| Epsilon (ε) | The strength dial for differential privacy. Smaller means stronger protection and usually less utility. |
| Delta (δ) | An additive slack in the approximate-DP probability inequality. It is not simply a probability that privacy fails; select and compose it for the stated protection contract. |
| Composition | Accounting for the joint disclosure from actual protected computations. Basic pure-DP ε values add; Gaussian zCDP uses a separate ρ account. |
| Group privacy | Converting a record guarantee to a protected unit with multiple records. Pure-DP ε scales by g; approximate-DP δ and Gaussian sensitivity require their own valid conversions. |
| Privacy accountant | The software that tracks total privacy loss across training, tuning and releases. It must cover the whole pipeline to be valid. |
| Blackwell ordering | A comparison under the same population, prior information and decision setting. One release reveals no more if it can be produced from the other without using protected data again. |
| Garbling / post-processing | Deriving one release from another by discarding or blurring information. If B is a garbling of A, B cannot reveal more than A. |
| Synthetic data | Artificially generated data resembling the real thing. Useful, but not automatically private. |
| Federated / secure computation | Computing across data held by separate custodians without pooling it. The outputs can still leak and must still be assessed. |
| Rho (ρ) | The parameter used by a zCDP account. It composes additively within that family and needs δ for conversion to an approximate-DP guarantee. |

### Process and protocol

| Term | Plain-language meaning |
| --- | --- |
| MRA / MRAP | The Model Release Assurance framework and its protocol. MRAP separates assessment, approval, authorisation and activation into distinct steps. |
| Portfolio registry | The authoritative common record of protected people, actual computations, dependencies, retained reservations and covered releases. Recipient labels do not reset the account. |
| Registry head | The current state of that registry. An assessment based on a stale head must be redone against the new state. |
| Release gateway | The technical component that verifies an authorisation and serves only the exact approved bytes and interface. |
| Fail closed | Missing, contradictory or unsupported evidence prevents clearance. This includes an inconclusive outcome; it need not mean a demonstrated privacy violation. |
| Red team | A team that deliberately attacks the system to find weaknesses. Their failure to find one is screening evidence, not approval. |

## Appendix D Reference framework crosswalk

This guide is framework-aligned, but it is not a substitute for certification, a jurisdiction-specific legal assessment, or the complete source standards.

| Guide area | Relevant external anchor |
| --- | --- |
| Data-first release experiment | MRA alpha 0.8.0 local review framework; explicit population, protected unit, mechanism, recipient and history binding |
| Least-information selection | Blackwell comparison of experiments; verified exact garbling certificates |
| Authorisation and activation | Proposed MRAP/1.0 lifecycle; bounded local prototypes do not establish production authorisation |
| Machine-checked core | Lean 4 authorisation-integrity, ideal-deployment and finite statistical-budget theorems |
| Governance, scope, accountability | NIST AI RMF GOVERN; ISO/IEC 42001 AI management system |
| Context and risk tiering | NIST AI RMF MAP; OECD lifecycle risk management |
| Testing and evidence | NIST AI RMF MEASURE; NIST Generative AI Profile |
| Treatment and monitoring | NIST AI RMF MANAGE; ISO Plan-Do-Check-Act |
| Privacy controls | ICO AI and data protection risk toolkit; applicable privacy law |
| Robustness, security and safety | OECD AI Principle 1.4; NIST trustworthiness characteristics |

## Sources and further reading

#### Project evidence through 28 September 2026

[P1] Current research plan and canonical working manuscript. academic/research-plan-20260926.md; academic/paper/mra-paper.tex. Private Model Export under Changing Tasks and Data. The current manuscript retains claim-relevant results and their limitations.

[P2] Central accounting and person-level model exports. academic/central-audit-validation-20260926/README.md. Matched accounting comparison: gate/benchmark-v2/REPORT.md. Utility follow-up: utility/analysis-v3/summary.csv and paired-contrasts.csv.

[P3] Bounded central release gate. docs/central-audit.md. Protection contract, trusted inputs, certificate families, reservations, byte binding, pooled recipients, revocation and deployment limits.

[P4] General trends in private model export after deletion. academic/unlearning-general-trends-20260925/README.md and analysis-confirmation-v2/tables.md. Completed 25 September 2026; record-level controlled study.

[P5] Repository README and current implementation status, 26 September 2026. Alpha 0.8.0. The console, private-export prototype and bounded central gate remain distinct workflows.

The paths above identify the original AI_ModeL_Check research tree. The publication source manifest maps the numbered experimental references to frozen source copies and includes selected context documents. It records both original and publication hashes where local machine paths were normalised. The manuscript remains background research; the snapshot is not its full dependency tree or an externally validated deployment certificate.

#### Singapore policy and legal context

- Smart Nation Singapore, Update to the National AI Strategy (2026). [Source](https://www.smartnation.gov.sg/initiatives/national-ai-strategy/)

- Singapore Statutes Online, Public Sector (Governance) Act 2018.

- Gov.sg, Public Sector (Governance) (Amendment) Bill explainer (2026). [Source](https://www.gov.sg/explainers/psga-bill/)

- MDDI, Government personal data protection laws and policies. [Source](https://www.mddi.gov.sg/other-pages/personal-data-protection-laws-and-policies/)

#### Framework and formal foundations

- Model Release Assurance alpha 0.8.0 repository and MRAP/1.0 candidate protocol; see project evidence [P1–P5].

- MRA formal mathematical foundations and scoped Lean 4 verification artefact. These proofs do not certify the current Python implementation or new central accounting mechanism.

- Blackwell, Equivalent Comparisons of Experiments (1953).

#### Attack literature

- Shokri et al., Membership Inference Attacks Against Machine Learning Models (IEEE S&P, 2017). [Source](https://arxiv.org/abs/1610.05820)

- Carlini et al., Extracting Training Data from Large Language Models (USENIX Security, 2021). [Source](https://www.usenix.org/conference/usenixsecurity21/presentation/carlini-extracting)

- Carlini et al., Extracting Training Data from Diffusion Models (2023). [Source](https://arxiv.org/abs/2301.13188)

- Nasr et al., Scalable Extraction of Training Data from (Production) Language Models (2023). [Source](https://arxiv.org/abs/2311.17035)

- Panfilov et al., Stealing Reasoning Traces from Proprietary LLM APIs (2026). [Source](https://arxiv.org/abs/2608.09867)

#### Reported incidents

- Ars Technica, Stable Diffusion memorizes some images, sparking privacy concerns (2023).

- The Register, ChatGPT repeating certain words can expose its training data (2023).

- TechCrunch, Samsung bans generative AI tools after internal data leak (2023).

#### Anonymisation and post processing

[A1] NIST SP 800-188, De-Identifying Government Datasets: Techniques and Governance (2023). [Source](https://csrc.nist.gov/pubs/sp/800/188/final)

[A2] Personal Data Protection Commission, Guide to Basic Anonymisation (2024 update). Practical technical guidance; its citation does not change the governing regime for public agencies. [Source](https://www.pdpc.gov.sg/help-and-resources/2018/01/basic-anonymisation)

[A3] Dwork and Roth, The Algorithmic Foundations of Differential Privacy (2014), Proposition 2.1 on post-processing. [Source](https://www.microsoft.com/en-us/research/publication/algorithmic-foundations-differential-privacy/)

#### Standards and guidance

- NIST, AI Risk Management Framework and associated resources. [Source](https://www.nist.gov/itl/ai-risk-management-framework)

- ISO/IEC 42001, AI management systems.

- ICO, AI and data protection risk toolkit.
