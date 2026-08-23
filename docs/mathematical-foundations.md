# Proof obligations and mathematical appendix

**Framework version:** 0.7.0
**Scope:** proof layer for [MRAP/1.0](model-release-assurance-protocol.md): finite release experiments, evidence-gate feasibility, incomplete portfolios, binomial evidence, and pairwise differential-privacy consequences

This document is the mathematical appendix to the candidate normative [Model Release Assurance Protocol](model-release-assurance-protocol.md). It is not itself a lifecycle protocol and none of its certificates is a production authorization. MRAP/1.0 defines the actors, signed messages, state machine, atomic registry transition, gateway enforcement and monitoring. Its authorization-integrity and finite statistical-accounting core is machine checked; the broader active-implies-acceptable statement remains a conditional engineering corollary with explicit adequacy and implementation-refinement obligations.

The appendix separates four kinds of statement that must not be conflated:

1. a **definition**, which fixes the decision game;
2. a **finite theorem**, which follows from explicitly encoded mathematical premises;
3. a **statistical guarantee**, which holds with declared coverage under a sampling model; and
4. an **empirical screen**, which reports only what a particular attack or test found.

The implementation is an offline reference system. A theorem below is usable at an MRAP evidence gate only when every premise is bound to the released artifact, interface, population, policy, evidence source, decision game, cumulative portfolio, and immutable protocol instance.

## 1. Finite decision games

### Definition 1: release experiment

Let

- \(\Omega=\{\omega_1,\ldots,\omega_m\}\) be a finite secret-state space;
- \(\mathcal Y=\{y_1,\ldots,y_n\}\) be the recipient's finite observation space; and
- \(K:\Omega\rightsquigarrow\mathcal Y\) be a row-stochastic channel, with
  \(K(y\mid\omega)=\Pr(Y=y\mid\omega)\).

The channel is the complete observable release protocol for the declared recipient. It is not merely the model file: preprocessing, endpoint behavior, explanations, retrieval, tools, state, related releases, and query budgets are part of \(K\) when observable.

### Definition 2: bounded decision problem

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

## 5. Incomplete release portfolios

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

## 6. Differential-privacy consequences

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

## 7. Binomial and low-FPR evidence

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

## 8. Implementation correspondence

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

## 9. Explicit non-claims and open proof obligations

The current repository does **not** prove:

- that a supplied finite channel is a faithful model of a continuous, adaptive, or changing deployment;
- that the world set, evidence laws, ambiguity set, population prior, threat list, or acceptability relation is complete or true;
- exact arithmetic for ordinary assessment tolerances and evidence endpoints—binary64 boundary decisions remain a high-priority gap;
- correctness of an external DP implementation merely because an accountant record exists;
- independence or exchangeability of empirical audit trials without a valid collection design;
- safe composition for an interactive LLM with unmodelled retrieval, tools, memory, updates, concurrency, or lifetime transcripts;
- scalable exact portfolio optimization beyond the configured finite decoder limit;
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

The broader model-release, attack, LLM, watermarking, and canary evidence base is reviewed in [the literature review](literature-review.md).
