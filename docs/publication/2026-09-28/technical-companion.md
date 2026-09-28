# Technical companion to Model privacy and release assurance

Publication edition 28 September 2026. This is supporting technical material for a proposed validation pilot. Its protocol requirements describe the candidate design and do not establish an adopted agency policy or production authorisation.

The guide presents the practical decisions. This companion retains the assumptions and calculations behind them. The complete model experiments are preserved in the separate experimental supplement and frozen evidence files.

## Evidence gate

#### Technical note on the evidence gate

For each mandatory threat, L is the strongest valid attack lower bound, U the strongest valid upper bound, and τ the tolerance. Use the same units, population, prior, interface and operating point.

L > τ: block on demonstrated exposure.

U ≤ τ: the threat may clear if scope, provenance and composition are complete.

Neither condition established: inconclusive. In particular, U > τ alone does not prove a violation.

L > U: investigate conflicting evidence before any decision.

Freeze the statistical failure budget across selected tests and threats. Individual confidence levels do not automatically provide the same confidence for the whole decision.


## Composition

#### Technical note on composition

The joint observation Y = (Y₁, …, Yₖ) can reproduce any component by discarding the others. It therefore Blackwell-dominates each component: for any fixed prior, actions and gain, the best achievable value from Y is at least that from Yᵢ.

Mutual information obeys the corresponding chain rule: the extra conditional-information terms are nonnegative. A positive term makes mutual information strictly larger, but need not improve every particular attack or decision problem. Mutual-information ordering alone does not establish Blackwell dominance.

Composition must describe the joint mechanism and all recipient knowledge. Marginal guarantees do not justify an independence assumption when separate computations share hidden randomness.


## Zero observed events

#### Technical note on zero observed events

For zero events in 3,000 independent, identically distributed Bernoulli trials, the rule of three gives an approximate one-sided 95% upper bound of 3/3000 = 0.001. The exact Clopper–Pearson upper bound is 1 − 0.05^(1/3000) = 0.000998079. The bound concerns that fixed method and sampling distribution. It does not bound the best possible attack, and adaptive selection or unrepresentative samples require different analysis.


## Conversion to person level guarantees

| Approved certificate | Conversion for one person |
| --- | --- |
| Pure DP per row | Multiply row ε by that person’s bounded row contribution. |
| Pure DP per person | Charge the certified person ε once for that source. |
| Gaussian zCDP per row | Use the justified Gaussian sensitivity conversion; r rows can require r² times the row ρ. |
| Gaussian zCDP per person | Charge the certified person ρ once. Do not multiply it again by row count. |

Keep pure ε and Gaussian ρ accounts separate. A ρ cap needs an explicit conversion and δ choice before it can be read as an (ε, δ) guarantee. A generic row-level claim is not enough to justify the Gaussian conversion. [P3]


## Release record notation

#### Technical note on The record in notation

Implementations may represent the same record as R = (A, I, Rc, P, T, Π, U, C, H, Pol, E, Trust, t_exp), corresponding respectively to artefact, interface, recipient, population, threat set, mechanism, utility requirement, controls, history, policy, evidence, trust profile and expiry time.


## Illustrative readmission release that remains on hold

### Worked example of a release that needs further evidence

This invented example shows how an apparently useful release can remain unapproved after redesign. Its membership calculation assumes a pure-DP mechanism with participation protection and a verified patient contribution bound; this is a hypothetical mechanism, not a claim about the current fixed-membership prototype. Identity calculations use a finite roster experiment with a uniform conditional prior. For the banded alternatives, the complete target-linked observation is one fixed band per model. The server returns the same stored band on repeat requests and permits no other queries or distinguishing outputs.

#### The request as submitted

| Contract field | Illustrative request |
| --- | --- |
| Artefact | XGBoost readmission model; 120 trees, depth 5; frozen model and pipeline hashes. |
| Interface proposed | Requested model file with unlimited local inspection and queries; compare separately with enforceable API alternatives. |
| Recipient and purpose | Named research institute with 12 staff; readmission research in a controlled enclave. Include any covered recipient who can pool earlier disclosures. |
| Population and unit | 41,882 episodes from 18,204 patients in a fixed illustrative snapshot. Patient participation is protected; each patient contributes at most g = 3 episodes. |
| Threat tolerances | Membership TPR ≤ 0.0100 at FPR ≤ 0.0010; identity success ≤ 0.0500 in the specified finite game; incremental attribute inference ≤ 0.0200. |
| Utility requirement | Balanced accuracy, lower confidence bound, must be at least 0.750 on a disjoint test split. |
| Controls and history | Enclave only; export disabled; 90-day expiry. One earlier release exists on the same population–secret pair. |

#### Technical note on What the tolerances mean

Each tolerance τ is a maximum, expressed at a stated operating point, and each is assessed separately.

Membership τ = 0.0100: the maximum permitted true-positive rate for deciding that a given patient was in the training data, evaluated at the agreed low false-positive operating point.

Identity τ = 0.0500: the maximum permitted probability of correctly singling out a specific patient from the recipient’s roster, measured on the worst case rather than the average.

Attribute τ = 0.0200: the maximum permitted increase in the recipient’s ability to infer the protected attribute, relative to an equally informed baseline that does not have the model.

#### Step 1 test the proposal that was actually requested

| Measure | Observed evidence | Decision |
| --- | --- | --- |
| Identity linkage | 15,140 observed signature groups among 18,204 candidates. A singleton identifies a target in the stipulated roster game; demonstrated success = 1.0000. | Block: exceeds τ = 0.0500. |
| Membership | 43 of 3,000 members caught; 0 of 4,000 nonmembers flagged. One-sided 97.5% bounds give FPR upper 0.000922 and TPR lower 0.01039, rounded conservatively. | Block: a valid attack floor exceeds τ = 0.0100. |
| Utility | Balanced accuracy 0.812; lower confidence bound 0.789. | Useful: exceeds the 0.750 floor. |

The two binomial bounds each use a 2.5% failure allowance, giving at least 95% joint coverage by a union bound. Assume a fixed attack threshold, independent representative trials within each group and no test-driven selection. The FPR upper bound is below 0.0010 and the TPR lower bound exceeds 0.0100, so this attack can block. Any larger family of tests needs its own frozen allocation.

Result. The full export is useful, but blocked on two separate threats. Usefulness does not override privacy. The team should look for a different release rather than weaken the evidence rule.

#### Step 2 compare useful alternatives

| Candidate | Identity, worst case | Membership evidence | Utility lower bound | Verdict |
| --- | --- | --- | --- | --- |
| Full model file | 1.0000 | floor 0.01039 | 0.789 | Blocked |
| Six-decimal score API | 1.0000 | floor 0.01039 | 0.789 | Blocked |
| Five-band API, ordinary training | 0.0023 | no approving ceiling | 0.774 | Inconclusive |
| Label-only, privacy-trained | 0.0002 | ceiling 0.0045 | 0.706 | Fails utility |
| Five-band API, privacy-trained at ε = 0.50 | 0.0023 | ceiling 0.0045 | 0.766 | Membership and identity only; history and attribute evidence still required |

The label-only option fails the utility floor. The ordinary five-band API lacks a membership ceiling. The privacy-trained five-band option clears the displayed standalone membership and finite identity checks, but that is only a provisional screen: the joint history and attribute threat still require evidence.

#### Step 3 Include the earlier release

Suppose the earlier release used pure ε = 0.50 per record and the proposed release uses another 0.50, under compatible participation adjacency and valid sequential composition. Their total is ε = 1.00 per record. A patient can contribute three episodes, so group privacy gives ε = 3.00 per patient.

At false-positive rate q = 0.0010, the bound TPR ≤ exp(3)q is 0.0201, above tolerance 0.0100. This upper bound does not clear membership, but it does not demonstrate that the redesigned release violates the limit. Without a stronger ceiling or a valid attack floor, the result is inconclusive.

Retuning the new release to ε = 0.25 gives total record ε = 0.75 and patient ε = 2.25. The resulting ceiling is 0.00948774, below 0.0100. Suppose the utility lower bound falls from 0.766 to 0.752, only 0.002 above its required floor. Membership now clears under the stated assumptions; the other threats still need assessment.

For the stipulated finite identity game, two five-band outputs create at most 25 joint cells. If the smallest joint cell contains 61 patients and the conditional prior within every cell is uniform, the maximum posterior identification probability is 1/61 = 0.0164. Additional auxiliary information or repeated query behaviour would require a different channel and could invalidate this ceiling.

#### Technical note on the illustrative bounds

Use pure DP with δ = 0, compatible participation adjacency and a verified contribution bound g = 3. Basic composition gives εpatient = 3(εold + εnew), and TPR ≤ min(1, exp(εpatient)q) at q = 0.0010.

Old 0.50 plus new 0.50: εpatient = 3.00 and U = 0.02008554. This does not clear τ = 0.0100; it is not a demonstrated violation.

Old 0.50 plus new 0.25: εpatient = 2.25 and U = 0.00948774. Membership clears if all assumptions hold.

Identity U = 1/61 = 0.01639344 applies only to the complete finite experiment and uniform conditional prior stipulated here.

A stronger applicable accountant may tighten a bound; improvement is not automatic. Approximate DP additionally requires correct δ composition and group conversion. Replay with controlled numerical error rather than treating exp(ε) as an exact fraction.

#### Step 4 record the constrained outcome

| Threat or condition | Bound or result | Threshold | Verdict |
| --- | --- | --- | --- |
| Membership | U = 0.00948774 under the hypothetical participation guarantee | τ = 0.0100 | Clear under stated assumptions |
| Identity linkage, joint | U = 1/61 in the stipulated finite identity game | τ = 0.0500 | Clear only for that complete game |
| Attribute inference, incremental | No valid ceiling established in this example | τ = 0.0200 | Inconclusive |
| Utility | lower bound = 0.752 | floor = 0.750 | Eligible; narrow margin |

Overall recommendation. Keep the retuned five-band candidate on hold. It meets the illustrative utility floor and the stated membership and identity checks, but the attribute threat lacks approving evidence. Obtain a release-bound attribute ceiling and verify all assumptions before authorisation. A favourable result for two threats cannot substitute for the missing third.


## MRAP lifecycle and proof boundaries

## Appendix B The release approval workflow

An assessment report, an optimisation report, a mathematical certificate, a signature or an audit entry is not an authorisation. The MRAP/1.0 protocol separates scientific assessment, governance approval, atomic authorisation and technical activation, so that no report and no client-side workflow can silently become permission to serve a model.

Current implementation status. MRA alpha 0.8.0 provides a local government audit console and non-authorising assessment workflows. Separate private-export and central-accounting prototypes exercise bounded mechanisms, durable reservations and exact-byte delivery. They have not replaced the console and do not establish authenticated agency custody, independent approval or production-wide enforcement. Lean proofs cover an abstract protocol, not the Python or cryptographic implementation. [P1, P3, P5]

### Proposed MRAP lifecycle

State names are protocol tokens and are reproduced here in their literal form.

| Stage | Meaning |
| --- | --- |
| DRAFT → REGISTERED | The submitter registers the immutable artefact, interface, recipient, population, candidates, policy and expected registry head. |
| PLAN_FROZEN → EVIDENCE_FROZEN | Freeze threats, statistical budgets, selection and stopping rules before collecting evidence. Reserve allowance before covered protected computations; bind truthful source evidence to the approved execution. |
| ASSESSED → OPTIMIZED | Every mandatory candidate-and-threat cell is marked clear, block or inconclusive. Utility and privacy feasibility precede deterministic least-information selection. |
| COMMIT_PENDING → AUTHORIZED | A role-authorised request must be committed atomically with the current portfolio and budget state. A local prototype receipt is not an authenticated agency authorisation. |
| AUTHORIZED → ACTIVE | The gateway independently checks the registry and re-measures the exact served bytes, interface, controls, expiry and revocation status. |
| ACTIVE → SUSPENDED / EXPIRED / REVOKED | Stop future service on expiry, suspension or revocation. Retain the history and charges for observations already delivered and for conservative reservations. |

Fail-closed lifecycle. Missing evidence, stale registry heads, binding mismatches, unsupported protocols, contradictory results or incomplete portfolios all lead to redesign, refusal, suspension or abort. No state may be skipped, and a stale-head retry must rebase against the new portfolio state.

### Evidence hierarchy

| Evidence type | What it can do |
| --- | --- |
| Verified guarantee, or valid analytical ceiling | May approve a bound threat: when assumptions, provenance and composition are all complete. |
| Exact release-bound calculation | May block or approve, depending on whether it establishes a floor or a ceiling. |
| Successful empirical attack | Blocks, when its valid floor exceeds tolerance. |
| Unsuccessful attack, or exploratory stress test | Identifies no demonstrated breach. Cannot approve. |
| Missing dependence, scope or provenance | Produces unassessed or inconclusive: never an assumption of independence or safety. |

### What is machine checked

The reference repository includes a pinned Lean 4 formalisation of a deliberately narrow core covering authorisation integrity, ideal deployment and finite statistical accounting. Within its abstract transition semantics, reaching an ACTIVE state requires registered gates, an authorisation request, a successful atomic commit, an advanced registry head, exact artefact and interface binding, and unexpired modelled time. The ideal gateway model rejects replay, stale heads, artefact or interface substitution, expiry, suspension and revocation. A finite-rational theorem bounds false-authorisation mass by the sum of registered component failure masses, without assuming independence between components.

Boundary of the formal proof. The proof does not establish that a model is substantively safe, that the evidence is scientifically adequate, or that the Python implementation, cryptography, identity service, database, gateway or deployment platform correctly refines the formal model. Policy completeness, worker truthfulness, real-world assumptions and implementation security all remain assurance obligations.

Implementation checks and independent replays test selected software behaviours. They are separate from the abstract Lean results and from the scientific adequacy of mechanism certificates, populations and evidence. None of these checks establishes complete vulnerability coverage or agency deployment readiness.


## Maintained specifications

The repository also maintains the [candidate MRAP protocol and conformance levels](../../model-release-assurance-protocol.md), [mathematical foundations](../../mathematical-foundations.md), [formal verification scope](../../formal-verification.md), and [versioned machine-readable schemas](../../../schemas/README.md). Conformance levels describe implementation claims within the candidate specification. They are not agency certification.
