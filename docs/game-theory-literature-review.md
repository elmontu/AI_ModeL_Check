# Game theory for model-release assurance: primary-source review

**Review date:** 2026-08-25
**Purpose:** determine which game-theoretic models can stress-test selected
institutional incentives without misdescribing either Bayesian decision theory
or the model-governance protocol as a strategic game
**Evidence policy:** peer-reviewed primary papers and official conference or
publisher records only

## 1. Review protocol and claim labels

This is a targeted rather than systematic review. It covers five questions:

1. How should a release authority allocate scarce audit and monitoring effort
   against strategic non-compliance?
2. When do penalties, audit probabilities, or rewards make compliance or
   evidence collection incentive compatible?
3. How should MRAP treat an attacker who chooses effort after observing a
   release and its controls?
4. What changes when actors have limited information, bounded rationality, or
   the deployed system changes the population it measures?
5. Which quantities require empirical or causal validation before they may be
   used as real-world game primitives?

Every literature statement below is classified as:

- **[S] Source result:** stated or proved by the cited primary source.
- **[I] MRAP inference:** a conservative implication drawn from source results;
  it is not a theorem of the cited paper.
- **[P] MRAP proposal:** a new specification choice requiring its own proof and
  validation.

Bibliographic metadata was cross-checked against official ACM, AAAI, IJCAI, or
PMLR records. A source is not used merely because a search snippet, generated
summary, or secondary survey mentions it. Stable identifiers, venue, year, and
the exact claim used are recorded in Section 7.

## 2. Main finding

MRAP's existing finite “decision games” are correctly formulated Bayesian
decision problems: a recipient chooses a decoder to maximize expected gain for
an exogenous prior, channel, action set, and gain function. They are useful for
quantifying information value and proving Blackwell-monotone transfer. They do
not, by themselves, constitute a multi-player strategic game.

The literature supports adding a separate, optional strategic stress-test layer while keeping
the existing decision problem as an inner attacker best response:

```text
authority commits to audit, monitoring, penalty, and release-control policy
        -> submitter/assessor choose compliance and costly evidence effort
        -> registry accepts or refuses using an imperfect audit signal
        -> attacker observes the released channel and chooses attack effort
        -> monitor observes signals and may suspend or revoke
```

This decomposition is an **[I] MRAP inference**, not a result established by any
single cited paper. The layer is subordinate to the governance core: it cannot
establish legitimate authority, procedural fairness, accountability,
contestation, affected-party acceptability, or authorization.

## 3. Findings from primary literature

### 3.1 Strategic prediction requires endogenous responses

Hardt, Megiddo, Papadimitriou, and Wootters model strategic classification as a
sequential game: the classifier is selected first and a person then changes
features at a cost to obtain a favorable outcome **[S]**. This supplies a real
leader–follower structure that MRAP's fixed observation channel does not yet
contain ([ITCS 2016, DOI 10.1145/2840728.2840730](https://doi.org/10.1145/2840728.2840730)).

Miller, Milli, and Hardt show that claims about whether strategic changes are
mere gaming or genuine improvement depend on causal structure; designing
incentives or cost functions can require solving a non-trivial causal-inference
problem **[S]** ([ICML 2020](https://proceedings.mlr.press/v119/miller20b.html)).
Consequently, a convenient “manipulation cost” must not be treated as a measured
real-world primitive without causal or behavioral validation **[I]**.

Perdomo, Zrnic, Mendler-Dünner, and Hardt formalize performative prediction,
where deploying a predictor changes the future data distribution, and define
performative stability **[S]** ([ICML 2020](https://proceedings.mlr.press/v119/perdomo20a.html)).
MRAP therefore cannot infer repeated-deployment stability from a one-shot game;
population response and retraining are separate registered dynamics **[I]**.

### 3.2 Audit games connect inspection, punishment, and strategic violations

Blocki, Christin, Datta, Procaccia, and Sinha model auditing as a Stackelberg
game in which the defender commits to inspection-resource allocation and a
punishment level, while an auditee chooses a violation target as a best response
**[S]**. Their motivating settings include hospitals and banks, and their
utilities include violation benefit, audit cost, breach loss, and punishment
cost ([IJCAI 2013, pp. 41–47](https://www.ijcai.org/Proceedings/13/Papers/017.pdf)).
Their later model treats multiple restricted audit resources and gives an FPTAS
for its non-convex optimization problem **[S]**
([AAAI 2015, DOI 10.1609/aaai.v29i1.9317](https://ojs.aaai.org/index.php/AAAI/article/view/9317)).

These papers justify modeling MRAP audit probability, resource restrictions,
violation benefits, detection consequences, and penalty costs explicitly
**[I]**. They do not establish that a particular MRAP penalty is lawful,
collectable, proportionate, or empirically deterrent.

### 3.3 Favorable Stackelberg tie-breaking can exaggerate assurance

Guo, Gan, Fang, Tran-Thanh, Tambe, and An show that the common strong
Stackelberg equilibrium convention—where a follower breaks best-response ties
in the leader's favor—can overstate the defender's guaranteed utility when the
desired response is not inducible **[S]**
([AAAI 2019, DOI 10.1609/aaai.v33i01.33012020](https://ojs.aaai.org/index.php/AAAI/article/view/4031)).

MRAP should therefore require strict incentive slack or adversarial tie-breaking
when claiming deterrence **[I]**. An equality such as “expected penalty equals
violation gain” is insufficient for a fail-closed protocol unless tie behavior
is separately justified **[P]**.

### 3.4 Real attackers may have limited surveillance and bounded rationality

An et al. study security games in which surveillance is costly and the attacker
forms beliefs from limited observations rather than perfectly observing the
defender's mixed strategy **[S]**
([AAAI 2012, DOI 10.1609/aaai.v26i1.8236](https://ojs.aaai.org/index.php/AAAI/article/view/8236)).
Shieh et al. report deployment of the PROTECT Stackelberg security-game system
for United States Coast Guard patrol scheduling and use a quantal-response
attacker model rather than perfect rationality **[S]**
([AAAI 2012, DOI 10.1609/aaai.v26i1.8436](https://ojs.aaai.org/index.php/AAAI/article/view/8436)).

These results show how real applications can connect player actions, resource
constraints, observation, and behavior to an operational setting **[I]**. They
do not imply that quantal response or any other behavioral model transfers to
model-extraction, membership-inference, insider, or LLM attackers. MRAP should
retain a worst-case best-response analysis and treat bounded-rational variants
only as registered sensitivity analyses **[P]**.

### 3.5 Evidence production is a principal–agent problem

Chen, Wu, Wu, and Yang model information acquisition as a Stackelberg
principal–agent interaction: the principal announces a scoring rule, then a
strategic agent selects costly effort and reports information **[S]**
([ICML 2023](https://proceedings.mlr.press/v202/chen23ah.html)). Their online
results do not directly solve MRAP assessment contracting, but they establish
that evidence quality cannot generally be separated from incentives and effort
cost **[I]**.

MRAP should therefore distinguish technical evidence validity from the
incentive compatibility of producing that evidence **[P]**. Signatures establish
who asserted a result; they do not ensure that the assessor exerted sufficient
effort or disclosed every adverse result.

### 3.6 Audit-time correctness does not prevent post-audit substitution

Yan and Zhang study active fairness auditing and explicitly analyze a
manipulation in which a company changes its model after answering audit queries
while remaining consistent with those queries **[S]**
([ICML 2022](https://proceedings.mlr.press/v162/yan22c.html)). This supports
MRAP's exact artifact/interface binding and gateway remeasurement as controls
against one form of post-audit substitution **[I]**. It does not prove that
hashes alone establish fairness or other substantive properties.

Waiwitlikhit et al. address the conflict between proprietary model/data secrecy
and auditability using commitments and zero-knowledge proofs **[S]**
([ICML 2024](https://proceedings.mlr.press/v235/waiwitlikhit24a.html)). This
supports treating cryptographic auditability as a possible implementation
layer **[I]**, not as evidence that the audited property or incentive model is
complete.

Raji et al. propose an end-to-end internal algorithmic-audit framework in which
development stages produce documentation for accountability **[S]**
([FAccT 2020, DOI 10.1145/3351095.3372873](https://doi.org/10.1145/3351095.3372873)).
This supports MRAP's lifecycle framing **[I]**, but the paper is not an
equilibrium or deterrence proof.

## 4. Consequences for MRAP

The reviewed literature supports the following changes:

1. Rename the existing object precisely as a **Bayesian release decision
   problem** while retaining “decision game” only as an acknowledged term of
   art.
2. Add an optional finite Stackelberg audit-and-release stress test with explicit players,
   timing, actions, information, payoffs, and solution concept.
3. Treat the existing Bayes leakage value as the attacker's optimal decoder
   value conditional on a chosen release/control, not as a complete attacker
   utility.
4. Add attack effort, query/compute cost, monitoring probability, sanctions,
   and abstention to the outer attack decision.
5. Require strict incentive margins and pessimistic tie handling.
6. Register an empirical or causal basis and uncertainty interval for every
   behaviorally interpreted payoff, cost, type distribution, detection
   probability, and response model.
7. Analyze payoff and belief sensitivity; fail closed when equilibrium release
   conclusions change within registered uncertainty sets.
8. Keep performative/repeated dynamics outside a one-shot theorem unless a
   transition law and equilibrium/stability claim are separately justified.
9. Never claim that formal protocol compliance is incentive compatible merely
   because unauthorized state transitions are excluded by the Lean type.
10. Never present a strategic certificate as a governance decision or permit it
    to override institutional authority, affected-party, legal, fairness, or
    other mandatory requirements.

## 5. What the literature does not justify

The review found no primary result establishing that one universal game or
payoff table covers every model family, deployment sector, attacker, or
regulatory environment. It also found no basis for deriving monetary values of
privacy, safety, fairness, or legal harm from MRAP's normalized decision gain.

Accordingly, the literature does **not** justify:

- calling the current fixed-channel Bayes problem a complete strategic game;
- assuming that submitters, assessors, attackers, or affected people are fully
  rational;
- assuming favorable best-response tie-breaking;
- translating attack success probability directly into money without a bound
  valuation model;
- treating legal penalties as credible when collection, jurisdiction, and
  enforcement probability are unmodeled;
- treating a fitted quantal-response coefficient as transportable across
  organizations or threat classes;
- claiming equilibrium uniqueness or real-world convergence from a one-shot
  finite model; or
- inferring social welfare from the release authority's utility alone.

## 6. Hallucination and overclaim controls

Future literature-driven changes to MRAP must satisfy this checklist:

1. **Primary record:** use an official proceedings, publisher, standards body,
   or author-hosted accepted manuscript; do not cite a generated summary as
   evidence.
2. **Metadata cross-check:** verify title, complete author list, venue, year,
   pages where available, and DOI or stable proceedings identifier.
3. **Claim localization:** record the abstract, theorem, section, or page that
   supports the claim.
4. **Three-way labeling:** distinguish source result **[S]**, MRAP inference
   **[I]**, and MRAP proposal **[P]**.
5. **No transfer by analogy:** a hospital-insider audit result does not become a
   theorem about external model attackers without a new mapping and proof.
6. **No theorem promotion:** simulation, case study, deployment report, and
   empirical association must not be described as a universal theorem.
7. **No equilibrium without a game:** identify players, timing, information,
   actions, utilities, beliefs/types, and solution concept before using the
   word “equilibrium.”
8. **Pessimistic ties:** use strict margins or worst-case follower tie-breaking
   unless inducibility is proved.
9. **Parameter provenance:** bind every real-world payoff/cost/probability to a
   source, population, time, unit, uncertainty set, and validation method.
10. **Contradiction search:** actively seek sources that weaken the proposed
    interpretation, including bounded rationality, imperfect surveillance,
    causal misspecification, manipulation, and post-audit substitution.
11. **Reproduction:** retain the search date, URLs/DOIs, inclusion decision, and
    exact framework claims affected.
12. **Scope statement:** state what remains unmodeled even after the update.

## 7. Claim-to-source ledger

| ID | Verified bibliographic record | Claim used by MRAP | Location checked | Transfer limit |
|---|---|---|---|---|
| `GT-01` | Blocki, Christin, Datta, Procaccia, Sinha, “Audit Games,” IJCAI 2013, pp. 41–47 | Audit allocation and punishment can be modeled as a defender–auditee Stackelberg game | Official IJCAI paper, abstract and Sections 1.1–1.2 | Hospital/bank audit motivation is not an AI-release validation |
| `GT-02` | Same authors, “Audit Games with Multiple Defender Resources,” AAAI 2015, DOI `10.1609/aaai.v29i1.9317` | Restricted multiple audit resources materially change the optimization; an FPTAS is supplied for their model | Official AAAI record and paper | Algorithm and guarantees apply only to that specified utility/action model |
| `GT-03` | Guo et al., “On the Inducibility of Stackelberg Equilibrium for Security Games,” AAAI 2019, DOI `10.1609/aaai.v33i01.33012020` | Strong-Stackelberg favorable ties can overstate guaranteed defender utility | Official AAAI abstract and paper | Does not itself choose MRAP's solution concept |
| `GT-04` | An et al., “Security Games with Limited Surveillance,” AAAI 2012, DOI `10.1609/aaai.v26i1.8236` | Perfect observation of the defender strategy can be unrealistic; surveillance may be costly and partial | Official AAAI abstract and issue metadata | Limited-surveillance model is not calibrated for model attacks |
| `GT-05` | Shieh et al., “PROTECT,” AAAI 2012, DOI `10.1609/aaai.v26i1.8436` | A Stackelberg security-game system with quantal response was operationally deployed for USCG patrol scheduling | Official AAAI abstract | Deployment evidence does not transfer its attacker model to MRAP |
| `GT-06` | Hardt, Megiddo, Papadimitriou, Wootters, “Strategic Classification,” ITCS 2016, DOI `10.1145/2840728.2840730` | Classifier choice and strategic feature response form a sequential game | DOI and accepted-paper record | Model users are not automatically equivalent to release submitters or attackers |
| `GT-07` | Miller, Milli, Hardt, “Strategic Classification is Causal Modeling in Disguise,” ICML 2020, PMLR 119:6917–6926 | Incentive/cost interpretations can require causal identification | Official PMLR abstract and metadata | Does not supply MRAP-specific causal variables |
| `GT-08` | Perdomo, Zrnic, Mendler-Dünner, Hardt, “Performative Prediction,” ICML 2020, PMLR 119:7599–7609 | Deployment can change future distributions; performative stability is a distinct equilibrium notion | Official PMLR abstract and metadata | Stability conditions require a registered response map |
| `GT-09` | Chen, Wu, Wu, Yang, “Learning to Incentivize Information Acquisition,” ICML 2023, PMLR 202:5194–5218 | Costly evidence acquisition can be modeled as a principal–agent Stackelberg interaction | Official PMLR abstract and metadata | Online scoring-rule result is not an MRAP assessor contract |
| `GT-10` | Yan, Zhang, “Active Fairness Auditing,” ICML 2022, PMLR 162:24929–24962 | A provider may change a model after answering audit queries; manipulation-proof estimation addresses a defined version-space threat | Official PMLR paper, introduction and metadata | Fairness-query results do not establish general model-release safety |
| `GT-11` | Waiwitlikhit et al., “Trustless Audits without Revealing Data or Models,” ICML 2024, PMLR 235:49808–49821 | Commitments and zero-knowledge proofs can reduce the auditability–secrecy conflict in their protocol | Official PMLR abstract and metadata | Cryptographic consistency does not establish evidence adequacy or incentives |
| `GT-12` | Raji et al., “Closing the AI Accountability Gap,” FAccT 2020, pp. 33–44, DOI `10.1145/3351095.3372873` | Internal algorithmic auditing can be organized across the development lifecycle with retained documentation | Official ACM record | Process framework is not a game-theoretic proof |

## 8. Review conclusion

The literature supports a meaningful but bounded supplement: MRAP can use a
finite Stackelberg audit-and-release stress test and principal–agent evidence
obligations to challenge selected institutional assumptions, while treating
Bayesian leakage as an inner attack value. It does not turn governance into an
equilibrium problem. Academic credibility depends on keeping authority,
accountability, legitimacy, contestation, and non-compensable duties in the
governance core while clearly limiting what strategic calculations can claim.

The proposed mathematical extension remains a design model until at least one
sector-specific case supplies defensible parameter ranges and demonstrates that
the release conclusion is robust across those ranges.
