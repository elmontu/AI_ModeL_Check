# Proof obligations and mathematical appendix

**Framework version:** 0.7.0
**Scope:** proof layer for [MRAP/1.0](model-release-assurance-protocol.md): finite release experiments, evidence-gate feasibility, optional strategic governance stress tests, incomplete portfolios, binomial evidence, and pairwise differential-privacy consequences

This document is the mathematical appendix to the candidate normative [Model Release Assurance Protocol](model-release-assurance-protocol.md). It is not itself a lifecycle protocol and none of its certificates is a production authorization. MRAP/1.0 defines the actors, signed messages, state machine, atomic registry transition, gateway enforcement and monitoring. Its authorization-integrity and finite statistical-accounting core is machine checked; the broader active-implies-acceptable statement remains a conditional engineering corollary with explicit adequacy and implementation-refinement obligations.

The appendix separates four kinds of statement that must not be conflated:

1. a **definition**, which fixes the decision game;
2. a **finite theorem**, which follows from explicitly encoded mathematical premises;
3. a **statistical guarantee**, which holds with declared coverage under a sampling model; and
4. an **empirical screen**, which reports only what a particular attack or test found.

The implementation is an offline reference system. A theorem below is usable at an MRAP evidence gate only when every premise is bound to the released artifact, interface, population, policy, evidence source, decision game, cumulative portfolio, and immutable protocol instance.

## 1. Finite Bayesian release decision problems

The phrase “decision game” is used in statistical decision theory, but the
object in this section has one optimizing decision maker facing an exogenous
experiment. It is not a multi-player strategic game and has no Nash,
Stackelberg, or sequential equilibrium. Section 5 adds a separate supplemental strategic
layer with explicit players, timing, payoffs, information, and a pessimistic
solution concept. The distinction follows the primary-source review in
[Game theory for model-release assurance](game-theory-literature-review.md).

### Definition 1: release experiment

Let

- \(\Omega=\{\omega_1,\ldots,\omega_m\}\) be a finite secret-state space;
- \(\mathcal Y=\{y_1,\ldots,y_n\}\) be the recipient's finite observation space; and
- \(K:\Omega\rightsquigarrow\mathcal Y\) be a row-stochastic channel, with
  \(K(y\mid\omega)=\Pr(Y=y\mid\omega)\).

The channel is the complete observable release protocol for the declared recipient. It is not merely the model file: preprocessing, endpoint behavior, explanations, retrieval, tools, state, related releases, and query budgets are part of \(K\) when observable.

### Definition 2: bounded Bayesian decision problem

Let \(\pi\in\Delta(\Omega)\) be the population-anchored prior, \(\mathcal A\) a finite action set, and \(g:\Omega\times\mathcal A\to[0,1]\) a bounded gain. A randomized decoder is a channel \(D:\mathcal Y\rightsquigarrow\mathcal A\). Its value is

\[
V_g(\pi,K;D)
=\sum_{\omega,y,a}\pi(\omega)K(y\mid\omega)D(a\mid y)g(\omega,a).
\]

The adversary's Bayes value is

\[
V_g(\pi,K)=\max_D V_g(\pi,K;D).
\]

Because the objective is linear in \(D\), a deterministic decoder attains the maximum in every finite problem. For exact guessing, \(\mathcal A=\Omega\) and \(g(\omega,a)=\mathbf 1\{a=\omega\}\).

A policy tolerance is meaningful only for a fully specified tuple

\[
\mathcal G=(\Omega,\pi,\mathcal A,g,K,\mathsf{sideinfo},\mathsf{population},\mathsf{recipient}).
\]

Changing any component changes the game.

## 2. Information ordering and safe transfer

### Definition 3: Blackwell dominance

For channels \(K_1:\Omega\rightsquigarrow\mathcal Y_1\) and \(K_2:\Omega\rightsquigarrow\mathcal Y_2\), write

\[
K_1\succeq_B K_2
\quad\Longleftrightarrow\quad
\exists Q:\mathcal Y_1\rightsquigarrow\mathcal Y_2\text{ such that }K_2=K_1Q.
\]

Thus \(K_2\) is obtained by state-independent post-processing, or garbling, of \(K_1\).

### Theorem 1: exact transfer soundness

If \(K_{\mathrm{assessed}}\succeq_B K_{\mathrm{released}}\), then for every prior, finite action set, and gain in \([0,1]\),

\[
V_g(\pi,K_{\mathrm{released}})
\le V_g(\pi,K_{\mathrm{assessed}}).
\]

**Proof.** Given any decoder \(D\) for the released experiment, \(QD\) is a decoder for the assessed experiment with exactly the same conditional action law and expected gain. Maximizing over assessed decoders cannot give a smaller value. \(\square\)

For finite experiments, Blackwell's comparison theorem also gives the converse: dominance for every bounded decision problem is equivalent to the existence of a garbling. MRA uses a replayable garbling matrix as a sufficient transfer certificate; it does not infer dominance from a few measured metrics.

### Proposition 1: approximate transfer

Suppose a kernel \(Q\) satisfies

\[
\eta=\max_{\omega\in\Omega}
d_{\mathrm{TV}}\!\left(
K_{\mathrm{released}}(\cdot\mid\omega),
(K_{\mathrm{assessed}}Q)(\cdot\mid\omega)
\right).
\]

Then, for every \(g\in[0,1]\),

\[
V_g(\pi,K_{\mathrm{released}})
\le V_g(\pi,K_{\mathrm{assessed}})+\eta.
\]

**Proof.** A released decoder composed with the two channels produces bounded state-conditional gains whose expectations differ by at most total variation. Average over \(\pi\), then apply Theorem 1 to \(K_{\mathrm{assessed}}Q\). \(\square\)

The penalty is one-sided and must be added to a transferred risk ceiling. It cannot be subtracted from an attack floor.

### Corollary 1: no universal privacy scalar

If two finite experiments are Blackwell-incomparable, the finite comparison theorem supplies bounded decision problems that rank them differently. Therefore no gain-independent scalar can preserve every privacy-relevant ordering. MRA consequently uses a vector of policy-bound threat constraints. A computed reversal witness establishes incomparability only for the supplied finite experiments and gains.

## 3. Evidence intervals and release decisions

For threat \(t\), let \(\theta_t=V_{g_t}(\pi_t,K_t)\) be the true recipient risk in the bound game and complete released portfolio. Evidence contributes an interval \([L_t,U_t]\subseteq[0,1]\):

- an attack floor supplies only \(L_t\);
- a formal or statistical ceiling supplies only \(U_t\);
- exact finite evidence supplies \(L_t=U_t\); and
- a screen supplies neither decision-valid endpoint.

Let \(\tau_t\) be the policy tolerance. MRA's per-threat rule is

\[
\begin{aligned}
L_t>\tau_t &\implies \mathsf{BLOCK},\\
U_t\le\tau_t\text{ with complete validated coverage}
&\implies \mathsf{CLEAR},\\
\text{otherwise}&\implies \mathsf{INCONCLUSIVE}.
\end{aligned}
\]

Conflicting validated bounds are inconclusive and require investigation.

### Theorem 2: simultaneous-coverage clearance bound

Let \(T\) be the complete set of mandatory threats. Suppose the evidence procedure guarantees

\[
\Pr\!\left(\forall t\in T:\theta_t\le U_t\right)\ge 1-\alpha,
\]

and the statistical gate returns `CLEAR` only when \(U_t\le\tau_t\) for every \(t\in T\). Then

\[
\Pr\!\left(
\mathsf{CLEAR}\ \land\
\exists t\in T:\theta_t>\tau_t
\right)\le\alpha.
\]

**Proof.** On the simultaneous-coverage event, clearance implies \(\theta_t\le U_t\le\tau_t\) for all mandatory threats. A false statistical clearance can therefore occur only when simultaneous coverage fails. \(\square\)

This is an inner-gate theorem, not a proof of end-to-end deployment safety. It provides no protection when the threat set is incomplete, the observation channel is wrong, the sampling model fails, the prior is unanchored, the candidate was selected outside the covered family, or the evidence source is false. MRAP/1.0 Section 13 states the machine-checked finite bound and the additional assumptions needed to compose declared statistical families with registry and gateway invariants.

### Selection requirement

If data are used to choose a model, threshold, subgroup, attack, interface, or release configuration, then either:

1. the confidence family covers every selectable candidate–threat claim; or
2. selection and final inference use independent data under a preregistered split.

Pointwise intervals for the selected winner do not become post-selection intervals merely because the selection rule is deterministic. Simultaneous protection is conservative but valid under arbitrary selection within the registered family.

## 4. Finite evidence-gate feasibility

This section analyzes whether any evidence-dependent gate could attain declared soundness and liveness in an explicitly finite model. It is a design-time meta-problem inside MRAP's `PLAN_FROZEN` and `ASSESSED` stages. The stochastic kernel below is not the operational MRAP state machine, and its output is not an `AuthorizationReceipt`.

Let \(\mathcal W\) be a finite set of possible worlds, \(\mathcal E\) a finite evidence-transcript space, \(\mathcal C\) a finite set of release configurations, and \(\bot\) refusal. World \(w\) has evidence law \(P_w(e)\) and acceptable set \(A_w\subseteq\mathcal C\). A randomized gate is a stochastic kernel

\[
x_{e,c}=\Pr(C=c\mid E=e),
\qquad c\in\mathcal C\cup\{\bot\}.
\]

Define

\[
u_w(x)=\sum_eP_w(e)\sum_{c\in\mathcal C\setminus A_w}x_{e,c}
\]

and

\[
\ell_w(x)=\sum_eP_w(e)\sum_{c\in A_w}x_{e,c}.
\]

Here \(u_w\) is unsafe-release probability and \(\ell_w\) is acceptable-release probability. Refusal contributes to neither.

For unsafe budget \(\alpha\), the optimal worst-world liveness is

\[
R^*(\alpha)=
\max_{x,r}\ r
\]

subject to

\[
\begin{aligned}
x_{e,c}&\ge0,&\sum_cx_{e,c}&=1 &&\forall e,\\
u_w(x)&\le\alpha &&&\forall w,\\
r&\le\ell_w(x) &&&\forall w:A_w\ne\varnothing.
\end{aligned}
\]

### Theorem 3: finite frontier completeness

The program above exactly characterizes all randomized evidence-dependent gates for the declared finite worlds, transcript laws, configurations, and acceptability sets. A target liveness \(1-\beta\) is achievable if and only if \(R^*(\alpha)\ge1-\beta\).

**Proof.** Every gate defines one feasible row-stochastic \(x\), and its unsafe and liveness probabilities are the displayed linear forms. Conversely, every feasible \(x\) is a gate with those probabilities. The equivalence follows by maximization. \(\square\)

The evidence-gate solver uses floating-point optimization only to search. It serializes a feasible rational primal and a rational dual upper certificate; verification replays their inequalities with exact fractions. A gap around the target yields `numerically_unresolved`, never a claim of feasibility or impossibility.

### Proposition 2: two-world indistinguishability obstruction

Let two worlds have disjoint acceptable sets. If a gate has \(u_{w_i}\le\alpha\) and \(\ell_{w_i}\ge1-\beta\) for \(i=0,1\), then

\[
\alpha+\beta\ge 1-d_{\mathrm{TV}}(P_{w_0},P_{w_1}).
\]

**Proof.** Let \(B\) be the event that the gate outputs a configuration acceptable in world \(w_0\). Then \(P_{w_0}(B)\ge1-\beta\), while disjointness makes \(B\) unsafe in world \(w_1\), so \(P_{w_1}(B)\le\alpha\). The difference between probabilities of any downstream event is at most the total variation of the transcript laws. \(\square\)

This proposition explains why refusal is sometimes unavoidable: sufficiently similar evidence laws cannot support both high liveness and low unsafe-release probability when the worlds demand incompatible actions.

## 5. Supplemental strategic stress tests for governance

This section supplies a deliberately small strategic stress test. It is a design-time
certificate for deployments that make incentive or deterrence claims; it is
not required merely to use the Bayesian leakage value in Section 1. The model
is motivated by Stackelberg audit games, strategic classification,
principal–agent information acquisition, limited-surveillance security games,
and the failure of optimistic follower tie-breaking documented in the
[review](game-theory-literature-review.md). It is not the governance core and
does not decide legitimate purpose, authority, affected-party acceptability,
accountability, contestation, or authorization. Those are institutional
requirements of the [governance core](governance-core.md).

### 5.1 Timing, players, and information

Let the release authority \(R\) commit publicly to a policy

\[
p=(c,q,F),
\]

where \(c\in\mathcal C\) is a release/control configuration, \(q\in[0,1]\) is
the effective probability that a material violation is detected before it can
produce the modeled harm, and \(F\ge0\) is the enforceable consequence imposed
when that violation is detected. The consequence may include a contractual
penalty, lost release benefit, mandatory remediation, or another application-
specific cost; MRAP does not assume that arbitrary monetary fines are lawful or
collectable.

A submitter has private type \(\theta\in\Theta\) and then chooses
\(a\in\{C,V\}\), where \(C\) means comply with the registered evidence/control
obligations and \(V\) means a material violation such as suppressing an adverse
result, using a cheaper unapproved control, or substituting an unaudited model.
Let \(G_\theta\ge0\) be the submitter's private incremental benefit from \(V\)
relative to \(C\), before detection consequences. The payoff difference is

\[
U_S(V\mid p,\theta)-U_S(C\mid p,\theta)=G_\theta-qF.
\]

This is an expected-utility abstraction. It requires risk neutrality over the
registered range; risk aversion, limited liability, non-monetary motives, and
probability weighting need separate models. The authority observes neither
\(\theta\) nor \(G_\theta\) exactly. It registers either a type distribution
\(\mu\) for a Bayesian analysis or an uncertainty interval
\(G_\theta\in[G_\theta^-,G_\theta^+]\) for robust assurance.

### Strategic theorem GT-1: strict robust deterrence

Fix a positive incentive margin \(\delta>0\). If

\[
qF\ge \sup_{\theta\in\Theta}G_\theta^+ + \delta,
\]

then \(C\) is the unique best response of every registered submitter type for
every gain value in its uncertainty interval.

**Proof.** For every admissible type and gain,

\[
U_S(V\mid p,\theta)-U_S(C\mid p,\theta)
=G_\theta-qF\le-\delta<0.
\]

Thus violation has strictly lower expected utility. \(\square\)

If \(\delta=0\), compliance is only weakly optimal at the boundary. MRAP does
not resolve that tie in the authority's favor. Conversely, if a registered type
can attain \(G_\theta>qF\), violation is its strict best response. These two
facts make the deterrence claim falsifiable instead of assuming compliance.

The detection probability in this theorem is the end-to-end probability of
detecting the defined violation in time, not the fraction of files nominally
sampled. If only \(q\in[q^-,q^+]\) is justified, the robust condition uses
\(q^-F\). If \(F\) is capped or enforcement is uncertain, the registered
effective consequence must be reduced accordingly.

### 5.2 Pessimistic authority objective

Let \(A(p)\) be the authority's audit, control, delay, enforcement, and
false-positive cost. Let \(H_\theta(c)\) be the harm when type \(\theta\)
violates under configuration \(c\) and the violation is not stopped. A minimal
authority loss is

\[
L_R(p,\theta,a)
=A(p)+\mathbf 1\{a=V\}(1-q)H_\theta(c).
\]

Define the submitter best-response correspondence

\[
BR_\theta(p)=\arg\max_{a\in\{C,V\}}U_S(a\mid p,\theta).
\]

MRAP's robust leader problem is the pessimistic Stackelberg program

\[
\min_{p\in\mathcal P}
\sup_{\theta\in\Theta}
\sup_{a\in BR_\theta(p)}L_R(p,\theta,a),
\]

where \(\mathcal P\) contains only technically feasible, legally authorized,
budget-compatible policies. Taking the worst loss over tied best responses
avoids the strong-Stackelberg assumption that the submitter breaks a tie in the
authority's favor. A Bayesian version may average over a validated \(\mu\), but
an average-case policy cannot replace a mandatory worst-type constraint when a
rare type can cause an unacceptable release.

This program is a specification, not a claim that its inputs are already known
or that its optimum is unique. A solution certificate must enumerate the finite
policy/type/action sets or provide independently replayable bounds.

### 5.3 Costly assessor effort

Let an assessor choose effort \(e\in\{L,H\}\) with costs \(k_L<k_H\). Suppose a
later independently verifiable scoring event occurs with probabilities
\(s_L<s_H\), and a contract pays reward \(R\ge0\) on that event. The assessor's
expected payoff difference is

\[
U_A(H)-U_A(L)=(s_H-s_L)R-(k_H-k_L).
\]

### Strategic theorem GT-2: high-effort incentive threshold

High effort is the unique best response exactly when

\[
(s_H-s_L)R>k_H-k_L.
\]

It is weakly optimal at equality and is not optimal when the inequality is
reversed.

**Proof.** Substitute the two expected rewards and compare their difference.
\(\square\)

This theorem does not prove truthful reporting. It applies only when the scoring
event is externally verifiable and the effort-to-score probabilities are
validated. When the authority never learns enough to score the report, this
contract model cannot be invoked. More elaborate proper-scoring or peer-
prediction mechanisms require their own assumptions and proofs.

### 5.4 Release controls and strategic attack effort

After observing the released configuration, a risk-neutral attacker chooses
either abstention \(0\) or an attack option \(z\in\mathcal Z\), where
\(\mathcal Z\) is finite and nonempty. Option \(z\) registers a
prior \(\pi_z\), bounded gain \(g_z\), economic or operational value scale
\(\lambda_z\ge0\), effort/query/data cost \(C_z(c)\), effective detection
probability \(d_z(c)\), and enforceable consequence \(P_z\ge0\). Its inner
optimal decoding value is the Section 1 quantity
\(V_{g_z}(\pi_z,K_c)\). The outer strategic payoff is

\[
U_T(z\mid c)
=\lambda_z V_{g_z}(\pi_z,K_c)
-C_z(c)-d_z(c)P_z,
\qquad U_T(0\mid c)=0.
\]

The normalized decision gain and the value scale are separate. A success
probability does not become a monetary loss merely by multiplying it by an
unvalidated number.

### Strategic theorem GT-3: attack abstention condition

Abstention is a best response if and only if

\[
\max_{z\in\mathcal Z}U_T(z\mid c)\le0.
\]

It is the unique best response when the maximum is strictly negative.

**Proof.** Abstention has payoff zero. It is weakly (strictly) preferred to all
finite alternatives exactly under the displayed weak (strict) inequalities.
\(\square\)

This condition is a deterrence statement, not a privacy ceiling. An attacker
with different values, costs, jurisdiction, or detection exposure is a
different registered type.

### Strategic theorem GT-4: Blackwell-safe control improvement

Consider two configurations \(c_1,c_2\). For attack option \(z\), suppose

1. \(K_{c_2}\succeq_B K_{c_1}\), so \(c_1\) is no more informative;
2. \(\lambda_z\ge0\); and
3. \(C_z(c_1)+d_z(c_1)P_z\ge C_z(c_2)+d_z(c_2)P_z\).

Then

\[
U_T(z\mid c_1)\le U_T(z\mid c_2).
\]

**Proof.** Theorem 1 gives
\(V_{g_z}(\pi_z,K_{c_1})\le V_{g_z}(\pi_z,K_{c_2})\). Multiplication by
\(\lambda_z\ge0\) preserves the inequality. The assumed non-information burden
is no smaller under \(c_1\); subtracting it completes the result. \(\square\)

This theorem is the formal bridge between the existing information ordering
and the supplemental strategic stress-test layer. It does not rank configurations when a less
informative interface is cheaper to attack, less detectable, or available to a
different recipient.

### 5.5 Real-world parameter contract

Every supplemental strategic certificate must bind the following record:

| Primitive | Required real-world basis | Fail-closed rule |
|---|---|---|
| Governance context | accountable owner, decision authority, independent reviewer, affected parties, governance objective, conflict controls, contestation, and incident/retirement authority | certificate has no governance-decision or authorization effect and cannot override a gate |
| Players/types | named organizations, recipient classes, jurisdictions, capabilities, and possible collusion | omitted material type makes the game incomplete |
| Timing/information | what each player observes before acting, including public policy and audit leakage | do not use a Stackelberg solution if commitment or observability is absent |
| \(G_\theta,k_e,C_z\) | accounting, measured effort, elicitation, incident data, or preregistered range with units | unsupported point values become uncertainty intervals |
| \(q,d_z,s_e\) | positive controls and prospective detection/validation experiments with simultaneous uncertainty bounds | use the adverse endpoint, not the point estimate |
| \(F,P_z\) | enforceable contractual, legal, technical, or access consequence after collection/jurisdiction limits | unenforceable consequences have zero deterrence credit |
| \(H_\theta,\lambda_z\) | policy-approved valuation model with affected-party perspective and sensitivity range | normalized risk scores are not monetary values |
| Response model | best response as the conservative baseline; any quantal/behavioral response separately fitted and validated | bounded-rational results are sensitivity evidence only |
| Equilibrium | exact solution concept, tie rule, existence/computation certificate, and robustness region | equilibrium-sensitive release remains inconclusive |

For a health-data model release, for example, a hospital release committee can
be the leader; the submitting team can choose documented compliance or a
defined shortcut; an independent assessor can choose costly review effort; and
recipient classes can choose query and inference attacks. This mapping is
real-world interpretable only after the hospital supplies defensible ranges for
the benefit of the shortcut, effective audit detection, enforceable
consequences, assessor effort/validation, attack resources, and harm. MRAP does
not invent those values. If the strict deterrence or release conclusion changes
within their registered intervals, the result is “inconclusive.”

#### Worked deployment mapping: synthetic health-model release

Consider a hospital preparing a synthetic-health model for controlled research
access. This is an illustrative mapping, not an empirical claim about any named
hospital or jurisdiction.

| Stage | Strategic primitive | Defensible evidence | Critical interpretation |
|---|---|---|---|
| Submitter may omit an adverse privacy result | \(G_\theta^+\) | maximum documented schedule saving, avoided control cost, and incentive payment attributable to that omission | use the upper bound; do not infer motive from salary alone |
| Independent rerun may detect the omission before release | \(q^-\) | lower simultaneous confidence bound from blinded planted-violation exercises using the actual review process | nominal audit coverage is not detection probability |
| Detection causes loss/remediation | \(F^-\) | minimum enforceable lost launch benefit plus mandatory remediation after legal and limited-liability review | reputational harm receives no credit unless its lower bound is justified |
| Assessor chooses review effort | \(s_H-s_L,k_H-k_L\) | randomized quality-control study or adjudicated historical tasks, with labor/time accounting | if no later scoring event exists, GT-2 is inapplicable |
| Research recipient chooses an inference attack | \(\lambda_z,C_z,d_z,P_z\) | registered value range, measured query/compute/data costs, monitor positive controls, and enforceability analysis | an anonymous or foreign attacker may have \(P_z=0\) |

The submitter deterrence claim clears only if the adverse-endpoint calculation
\(q^-F^-\ge G_\theta^++\delta\) holds for every material submitter type. If it
fails, MRAP does not assume honesty; it retains independent replay, immutable
evidence closure, and gateway binding.

For an attacker against whom no consequence can be enforced, \(P_z=0\), so

\[
U_T(z\mid c)=\lambda_zV_{g_z}(\pi_z,K_c)-C_z(c).
\]

Detection by itself then supplies no deterrence in this utility model. It helps
only if it stops access, raises attack cost, reduces the observable channel, or
creates a genuinely enforceable consequence. Thus a public or cross-border
health-model endpoint will often require information-reducing controls and
strict query enforcement rather than a claim that monitoring will deter a
rational attacker.

This mapping demonstrates why one payoff table cannot cover the submitting
team, assessor, approved researcher, anonymous external attacker, and colluding
recipient. They require separate types, information sets, costs, and
enforcement assumptions.

### 5.6 Scope boundaries

This one-shot model does not establish performative stability, repeated-game
reputation, learning across releases, coalition-proofness, bribery resistance,
risk-sensitive utility, behavioral transportability, or social welfare. A
repeated or performative claim must define the response transition law, horizon,
discounting, learning rule, and its own equilibrium or stability concept.

## 6. Incomplete release portfolios

For releases \(j=1,\ldots,k\), marginal channels do not determine the joint transcript channel. Let \(K\) denote a candidate joint channel over \(\mathcal Y_1\times\cdots\times\mathcal Y_k\), and let \(\Gamma\) be the ambiguity polytope defined by normalization, non-negativity, marginal intervals, coupling assumptions, and registered joint-event constraints.

The robust portfolio risk is

\[
\overline V_g(\pi,\Gamma)
=\sup_{K\in\Gamma}V_g(\pi,K).
\]

### Proposition 3: marginal evidence is not generally compositional

Two binary releases can each be independent of a binary secret while their pair reveals it exactly. For example, with independent uniform \(S,R\), let \(Y_1=R\) and \(Y_2=S\oplus R\). Then

\[
V_{\mathrm{guess}}(S;Y_1)=V_{\mathrm{guess}}(S;Y_2)=\tfrac12,
\qquad
V_{\mathrm{guess}}(S;Y_1,Y_2)=1.
\]

Therefore independent per-release checks cannot establish a joint ceiling without a justified coupling model or direct joint evidence.

### Theorem 4: decoder-complete finite optimization

Let \(\mathcal D_{\mathrm{det}}\) be the finite set of deterministic decoders from joint transcripts to actions. Then

\[
\overline V_g(\pi,\Gamma)
=\max_{d\in\mathcal D_{\mathrm{det}}}
\ \sup_{K\in\Gamma}V_g(\pi,K;d).
\]

For fixed \(d\), the inner problem is a linear program in the channel cells. Enumerating every deterministic decoder and solving each LP is therefore complete for the declared finite ambiguity set.

**Proof.** A deterministic decoder attains \(V_g(\pi,K)\) for each fixed \(K\). Because \(\mathcal D_{\mathrm{det}}\) is finite,
\(\sup_K\max_d f(K,d)=\max_d\sup_K f(K,d)\). The fixed-decoder objective and all constraints defining \(\Gamma\) are linear. \(\square\)

The exact method is exponential in the number of joint transcripts. The envelope method is a replayable conservative upper bound, not an exact optimum.

### Monotonicity laws

If \(\Gamma_1\subseteq\Gamma_2\), then

\[
\overline V_g(\pi,\Gamma_1)\le\overline V_g(\pi,\Gamma_2).
\]

More valid evidence can shrink ambiguity and improve a robust ceiling. By contrast, for a fixed true mechanism, adding a release to the observable portfolio cannot reduce adversarial value because a decoder may ignore it.

For sequential assurance events \(F_j\) satisfying

\[
\Pr(F_j\mid F_1^c,\ldots,F_{j-1}^c)\le\alpha_j,
\]

the chain rule and union bound give

\[
\Pr\!\left(\bigcup_{j=1}^J F_j\right)\le\sum_{j=1}^J\alpha_j.
\]

Independence is not required, but the conditional guarantees and ledger must be real.

## 7. Differential-privacy consequences

Let \(P_s\) be the complete output law conditional on secret state \(s\in\Omega\). The finite-secret result requires the symmetric pairwise condition

\[
P_s(B)\le e^\epsilon P_{s'}(B)+\delta
\quad
\forall s,s'\in\Omega,\ \forall B.
\]

This premise is stronger than checking selected state pairs. It must follow from the declared adjacency, composition, protected unit, and complete pipeline.

### Theorem 5: membership ROC ceiling

For two neighboring hypotheses, let \(q\) be false-positive rate and \(r\) true-positive rate for any test. Symmetric \((\epsilon,\delta)\)-DP implies

\[
r\le e^\epsilon q+\delta
\]

and

\[
r\le1-e^{-\epsilon}(1-q-\delta).
\]

**Proof.** Apply DP to the test's positive event for the first inequality. Apply the reverse ordered-pair inequality to the complement and rearrange for the second. \(\square\)

Thus

\[
r\le\min\!\left\{
e^\epsilon q+\delta,
1-e^{-\epsilon}(1-q-\delta)
\right\}.
\]

### Theorem 6: finite-secret Bayes exact-guess ceiling

Assume pairwise \((\epsilon,\delta)\)-DP, a prior \(\pi\), and

\[
p\ge\max_s\pi(s),\qquad 0<p<1.
\]

Then every decoder satisfies

\[
V_{\mathrm{guess}}(\pi,K)
\le
B(\epsilon,\delta,p)
:=
\frac{e^\epsilon p+\delta(1-p)}{1-p+e^\epsilon p}.
\]

**Proof.** Let \(S_i\) be the decoder region assigned to state \(i\), allowing randomized regions by replacing indicators with decision probabilities. Write

\[
A=\sum_i\pi_iP_i(S_i).
\]

For every \(j\ne i\), DP gives \(P_i(S_i)\le e^\epsilon P_j(S_i)+\delta\). Average these inequalities with weights \(\pi_j/(1-\pi_i)\), multiply by \(\pi_i\), and define

\[
r_i=\frac{e^\epsilon\pi_i}{1-\pi_i},
\qquad
r=\max_i r_i\le\frac{e^\epsilon p}{1-p}.
\]

Summing over \(i\) and using \(\sum_{i\ne j}P_j(S_i)=1-P_j(S_j)\) yields

\[
A\le r(1-A)+\delta.
\]

Hence \(A\le(r+\delta)/(1+r)\). The right-hand side is increasing in \(r\), so substitution of the prior-mass cap gives \(B(\epsilon,\delta,p)\). \(\square\)

For a uniform prior on \(m\) states, \(p=1/m\) and

\[
B(\epsilon,\delta,1/m)
=\frac{e^\epsilon+(m-1)\delta}{e^\epsilon+m-1}.
\]

For two equal-prior membership hypotheses this becomes

\[
\frac{e^\epsilon+\delta}{e^\epsilon+1}.
\]

The 0.7.0 implementation requires `metric_parameters.maximum_secret_prior` in the policy and threat contracts, a source-bound `maximum_secret_prior`, `secret_prior_bound_validated: true`, and `pairwise_secret_relation_validated: true`. It computes the stable equivalent

\[
\frac{p+\delta(1-p)e^{-\epsilon}}
{p+(1-p)e^{-\epsilon}},
\]

which does not overflow at large finite \(\epsilon\). The previous cardinality-only formula silently assumed a uniform prior and is no longer clearance-valid without the numerical prior premise.

## 8. Binomial and low-FPR evidence

For \(X\sim\mathrm{Binomial}(n,p)\) and observed \(X=k\), the one-sided Clopper–Pearson limits invert exact binomial tests. With tail error \(\gamma\),

\[
L(k,n;\gamma)=
\begin{cases}
0,&k=0,\\
F_{\mathrm{Beta}(k,n-k+1)}^{-1}(\gamma),&k>0,
\end{cases}
\]

and

\[
U(k,n;\gamma)=
\begin{cases}
1,&k=n,\\
F_{\mathrm{Beta}(k+1,n-k)}^{-1}(1-\gamma),&k<n.
\end{cases}
\]

If a registered family has tail allocations \(\gamma_1,\ldots,\gamma_M\) with \(\sum_i\gamma_i\le\alpha\), the union bound gives simultaneous coverage at least \(1-\alpha\), without independence.

At target FPR \(q\), an empirical operating point is accepted only when its FPR upper limit is at most \(q\). The associated TPR lower limit is an attack floor. Neither a low TPR nor failure to attain the requested FPR is an upper bound on privacy.

The binomial model requires independent Bernoulli trials, or a separately justified model for dependence. Repeated prompts, clustered people, adaptive thresholds, and reused records do not become independent trials by being placed in separate rows.

## 9. Implementation correspondence

| Mathematical object | Implementation | Status |
|---|---|---|
| Finite channel, prior, decision value | `decision_theory.py` | Implemented for finite binary64 inputs |
| Exact/approximate garbling witness | `decision_theory.py` | Forward certificate replay; approximate penalty implemented |
| Threat interval gate | `decision.py` | Fail closed; boundary comparisons still use binary64 |
| Source/game/population binding | `engine.py`, `integrity.py` | Implemented with hashes and exact source payload matching |
| Finite evidence-gate soundness–liveness frontier | `protocol_feasibility.py` | Design-time meta-analysis; rational primal/dual replay after numerical search |
| Incomplete-portfolio robust bound | `incomplete_portfolio.py` | Exact decoder enumeration or conservative envelope |
| Simultaneous multinomial marginals | `portfolio_statistics.py` | Bonferroni Clopper–Pearson family with ledger checks |
| Membership and finite-secret DP ceilings | `analyzers/dp.py` | Stable formulas; prior cap and pairwise premises required |
| Empirical attack floors | `analyzers/attack.py`, `controlled_inference.py` | May block; cannot clear |
| XGBoost and LLM tests | experiment/linter scripts | Screens only; no general theorem |
| Supplemental Stackelberg audit/release and attack-effort stress test | `strategic_assurance.py` and `run_strategic_assurance_experiment.py` | Exact-rational adverse-endpoint certificates, governance-context binding, no-decision/no-authorization markers, provenance checks, replay, and synthetic stress test implemented; no behavioral calibration or production parameter registry |

## 10. Explicit non-claims and open proof obligations

The current repository does **not** prove:

- that a supplied finite channel is a faithful model of a continuous, adaptive, or changing deployment;
- that the world set, evidence laws, ambiguity set, population prior, threat list, or acceptability relation is complete or true;
- exact arithmetic for ordinary assessment tolerances and evidence endpoints—binary64 boundary decisions remain a high-priority gap;
- correctness of an external DP implementation merely because an accountant record exists;
- independence or exchangeability of empirical audit trials without a valid collection design;
- safe composition for an interactive LLM with unmodelled retrieval, tools, memory, updates, concurrency, or lifetime transcripts;
- scalable exact portfolio optimization beyond the configured finite decoder limit;
- incentive compatibility, deterrence, equilibrium selection, or social welfare without a complete and validated Section 5 game record;
- transportability of payoff, detection, effort, or bounded-rationality parameters across actors, sectors, populations, or time;
- exhaustive configuration search unless the generator and enumeration certificate are replayed; or
- production authorization, key custody, identity, atomic portfolio commits, monitoring, or accreditation.

Unsupported premises produce `inconclusive`, not a mathematical presumption of safety.

## Primary foundations

- Blackwell. [Equivalent Comparisons of Experiments](https://doi.org/10.1214/aoms/1177729032). *Annals of Mathematical Statistics*, 1953.
- Neyman and Pearson. [On the Problem of the Most Efficient Tests of Statistical Hypotheses](https://doi.org/10.1098/rsta.1933.0009). *Philosophical Transactions of the Royal Society A*, 1933.
- Clopper and Pearson. [The Use of Confidence or Fiducial Limits Illustrated in the Case of the Binomial](https://doi.org/10.1093/biomet/26.4.404). *Biometrika*, 1934.
- Sion. [On General Minimax Theorems](https://doi.org/10.2140/pjm.1958.8.171). *Pacific Journal of Mathematics*, 1958.
- Dwork, McSherry, Nissim, and Smith. [Calibrating Noise to Sensitivity in Private Data Analysis](https://doi.org/10.1007/11681878_14). TCC 2006.
- Wasserman and Zhou. [A Statistical Framework for Differential Privacy](https://doi.org/10.1198/jasa.2009.tm08651). *JASA*, 2010.
- Dwork and Roth. [The Algorithmic Foundations of Differential Privacy](https://doi.org/10.1561/0400000042). *Foundations and Trends in Theoretical Computer Science*, 2014.
- Dong, Roth, and Su. [Gaussian Differential Privacy](https://doi.org/10.1111/rssb.12454). *JRSS B*, 2022.
- Berk, Brown, Buja, Zhang, and Zhao. [Valid Post-Selection Inference](https://doi.org/10.1214/12-AOS1077). *Annals of Statistics*, 2013.
- Blocki, Christin, Datta, Procaccia, and Sinha. [Audit Games](https://www.ijcai.org/Proceedings/13/Papers/017.pdf). *IJCAI*, 2013.
- Guo, Gan, Fang, Tran-Thanh, Tambe, and An. [On the Inducibility of Stackelberg Equilibrium for Security Games](https://doi.org/10.1609/aaai.v33i01.33012020). *AAAI*, 2019.
- Miller, Milli, and Hardt. [Strategic Classification is Causal Modeling in Disguise](https://proceedings.mlr.press/v119/miller20b.html). *ICML*, 2020.
- Chen, Wu, Wu, and Yang. [Learning to Incentivize Information Acquisition](https://proceedings.mlr.press/v202/chen23ah.html). *ICML*, 2023.

The broader model-release, attack, LLM, watermarking, and canary evidence base is reviewed in [the literature review](literature-review.md).
