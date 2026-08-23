# Literature review: privacy assurance for model releases

**Evidence cutoff:** 2026-08-22
**Review type:** targeted narrative review of primary peer-reviewed work and selected authoritative standards

## Executive synthesis

The literature supports MRA's core fail-closed direction, but it also narrows what the current evidence can legitimately claim.

1. **Empirical attacks are lower-bound evidence.** A successful membership, extraction, reconstruction, or canary attack establishes leakage under the tested decision game. An unsuccessful attack shows only that this attack failed under this interface, population, side information, and budget. It is not an upper bound on privacy. This distinction follows both the attack literature and the game-based systematization of privacy risks by [Salem et al. (IEEE S&P 2023)](https://www.microsoft.com/en-us/research/publication/sok-let-the-privacy-games-begin-a-unified-treatment-of-data-inference-privacy-in-machine-learning/).
2. **Operational metrics matter more than average accuracy.** Membership inference should be evaluated at preregistered low false-positive rates, with enough nonmembers to estimate the tail, realistic membership priors, simultaneous uncertainty, and record-level or subgroup heterogeneity. AUROC or balanced accuracy alone can hide the relevant risk ([Jayaraman et al., PoPETs 2021](https://petsymposium.org/popets/2021/popets-2021-0031.php); [Song and Mittal, USENIX Security 2021](https://www.usenix.org/conference/usenixsecurity21/presentation/song); [Carlini et al., IEEE S&P 2022](https://doi.org/10.1109/SP46214.2022.9833649)).
3. **Formal differential privacy and empirical auditing have different roles.** A correctly scoped and implemented DP mechanism can provide an upper bound; canary or adversarial audits provide implementation-sensitive lower bounds and can expose bugs. Neither substitutes for the other ([Nasr et al., USENIX Security 2023](https://www.usenix.org/conference/usenixsecurity23/presentation/nasr); [Steinke et al., NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/9a6f6e0d6781d1cb8689192408946d73-Abstract-Conference.html)).
4. **Evidence specific to modern released XGBoost ensembles is limited.** Peer-reviewed work establishes membership leakage for general and tree models, and extraction risk for decision-tree APIs, but the evidence base is much deeper for neural networks than for current GBDT artifacts. The local worker is therefore best described as a reference-loss membership **screen**, not a complete XGBoost privacy audit or a LiRA implementation.
5. **Canary studies answer different questions depending on their design.** Rank/exposure canaries, randomized IN/OUT DP-audit canaries, and naturalistic extraction probes are not interchangeable. Each needs its own preregistered evidence contract: exposure canaries require a randomness space, format, tokenizer, insertion ledger, and scoring interface; randomized IN/OUT audits require committed inclusion randomization and a scoring rule; naturalistic probes require a bound recipient interface, success rule, and query budget.
6. **LLM membership evidence is highly design-sensitive.** Verbatim extraction is real, but pretraining-membership benchmarks can be confounded by temporal or distribution shift and fuzzy membership labels. Matched controls and near-duplicate analysis are mandatory; null attack results remain inconclusive ([Duan et al., COLM 2024](https://openreview.net/forum?id=av0D19pSkU)).
7. **A watermark hit is not proof of authorship.** It means only that the registered detector rejected its declared null for that text under the specified key, tokenizer, canonicalization, null population, and calibrated threshold. It does not authenticate the generation channel. Repeated contexts can invalidate nominal null assumptions; span searches and multiple keys introduce multiplicity; adaptive attackers can learn, remove, or spoof studied schemes ([Fernandez et al., IEEE WIFS 2023](https://doi.org/10.1109/WIFS58808.2023.10374576); [Jovanović et al., ICML 2024](https://proceedings.mlr.press/v235/jovanovic24a.html)).
8. **Interactive services must be assessed as complete protocols.** Model version, tokenizer, system prompt, decoding, RAG, tools, memory, filtering, rate limits, concurrency, retention, updates, and the lifetime transcript all alter the observable channel. A one-shot base-model study cannot authorize a chat service.

## Review method and limitations

The search prioritized official proceedings and accepted-paper records from USENIX Security, IEEE Symposium on Security and Privacy, IEEE CSF, ACM CCS/FAccT, NDSS, PoPETs, ICML, NeurIPS, ICLR, COLT, ACL, EMNLP, and EACL. PMLR, NeurIPS proceedings, ACL Anthology, USENIX, IEEE/ACM DOI records, and accepted OpenReview records were preferred over aggregators. NIST publications were included as authoritative implementation and governance context.

Included sources are primary empirical or theoretical papers directly relevant to model-release privacy, attack evaluation, GBDT/tree interfaces, LLM memorization, canaries, or text watermarks. Surveys, theses, unaccepted submissions, vendor posts, and unsupported product claims were excluded from the main synthesis. A few systematization papers and standards are retained because they define threat-model or assurance structure rather than report a new attack.

This is a targeted narrative review, not a PRISMA systematic review or meta-analysis. The literature uses heterogeneous datasets, interfaces, adversary knowledge, base rates, metrics, and model families, so numerical effect sizes should not be pooled or transferred without a new validation study. Absence from this review is not evidence that a paper or attack does not exist.

## Conceptual foundations

MRA's use of information ordering has a sound statistical foundation. Blackwell's comparison of experiments says that one experiment is no more informative than another when it can be obtained by post-processing, or garbling, the other ([Blackwell, *Annals of Mathematical Statistics*, 1953](https://doi.org/10.1214/aoms/1177729032)). This supports the framework rule that evidence can transfer from an assessed interface to a less informative released interface only when the safe direction is replayably established. It does not prove that a finite empirical experiment fully captures a real deployment.

Differential privacy supplies a different kind of claim: neighboring datasets induce boundedly different output distributions ([Dwork et al., TCC 2006](https://doi.org/10.1007/11681878_14)). Repeated or adaptive releases consume privacy through composition ([Kairouz, Oh, and Viswanath, ICML 2015](https://proceedings.mlr.press/v37/kairouz15.html)). Consequently, an accountant is meaningful only when the protected unit, adjacency, sampling, preprocessing, model selection, stopping, post-processing, and all related releases are inside its declared scope. [NIST SP 800-226](https://csrc.nist.gov/pubs/sp/800/226/final) likewise treats a practical DP guarantee as a stack of assumptions and implementation choices, not merely an epsilon value.

Privacy attacks must also be represented as explicit games. The taxonomy in [Salem et al. (IEEE S&P 2023)](https://www.microsoft.com/en-us/research/publication/sok-let-the-privacy-games-begin-a-unified-treatment-of-data-inference-privacy-in-machine-learning/) shows that superficially similar membership, attribute, property, and reconstruction results can differ in challenger construction, adversary knowledge, observations, and success conditions. This strongly supports MRA's decision-game contracts and argues against converting a metric name alone into policy evidence.

## Membership, extraction, and model-release evidence

### What the attack literature establishes

[Shokri et al. (IEEE S&P 2017)](https://www.ieee-security.org/TC/SP2017/papers/313.pdf) demonstrated black-box membership inference by learning differences between model behavior on members and nonmembers. [Yeom et al. (IEEE CSF 2018)](https://doi.org/10.1109/CSF.2018.00027) connected simple loss-threshold attacks to overfitting and influence, while also showing that overfitting is sufficient but not necessary for leakage. [Salem et al. (NDSS 2019)](https://doi.org/10.14722/ndss.2019.23119) weakened assumptions about shadow models, target architectures, and matched data.

A released model artifact creates a stronger observation surface than a prediction-only API. [Nasr, Shokri, and Houmansadr (IEEE S&P 2019)](https://doi.org/10.1109/SP.2019.00065) developed passive and active white-box membership attacks against deep-learning models, while [Leino and Fredrikson (USENIX Security 2020)](https://www.usenix.org/conference/usenixsecurity20/presentation/leino) showed that internal feature use can support calibrated white-box membership inference even when black-box behavior appears to generalize. These results concern neural networks rather than GBDTs, so transfer to XGBoost must be tested, but they establish that a full-artifact profile cannot be represented by an API-only attack.

Later work changed how these attacks should be evaluated. [Jayaraman et al. (PoPETs 2021)](https://petsymposium.org/popets/2021/popets-2021-0031.php) emphasized realistic, skewed membership priors and positive predictive value. [Song and Mittal (USENIX Security 2021)](https://www.usenix.org/conference/usenixsecurity21/presentation/song) showed that aggregate performance can obscure highly vulnerable records and that defenses require adaptive evaluation. [Carlini et al. (IEEE S&P 2022)](https://doi.org/10.1109/SP46214.2022.9833649) argued for true-positive rate at very low false-positive rates and introduced LiRA, a per-example likelihood-ratio attack calibrated with reference models. [Ye et al. (ACM CCS 2022)](https://doi.org/10.1145/3548606.3560675) further formalized membership attacks as hypothesis tests under explicit reference and target assumptions.

These findings imply four minimum reporting requirements:

- TPR at one or more preregistered low-FPR operating points, with an upper one-sided confidence bound on attained FPR and a lower one-sided confidence bound on TPR;
- the member prior or base-rate range and resulting positive predictive value;
- per-record, subgroup, or tail-risk summaries rather than only a global mean;
- complete disclosure of reference-data access, shadow/reference construction, threshold selection, and every comparison in the selected family.

Model extraction is a related but distinct threat. [Tramèr et al. (USENIX Security 2016)](https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/tramer) extracted high-fidelity models, including decision trees, from prediction APIs; hiding confidence values did not eliminate the threat in their setting. [Jagielski et al. (USENIX Security 2020)](https://www.usenix.org/conference/usenixsecurity20/presentation/jagielski) separated high-accuracy substitutes from high-fidelity reconstruction. An easily copied model does not necessarily leak individual training membership, and a hard-to-copy model may still leak it. MRA should maintain separate policy games for model confidentiality, membership, attribute inference, and reconstruction.

### Formal upper bounds and empirical lower bounds

Empirical auditing can test whether a claimed DP implementation leaks at least a certain amount. [Nasr et al. (USENIX Security 2023)](https://www.usenix.org/conference/usenixsecurity23/presentation/nasr) produced tight audits under specified, sometimes strong, observation assumptions and exposed implementation bugs. [Steinke, Nasr, and Jagielski (NeurIPS 2023)](https://proceedings.neurips.cc/paper_files/paper/2023/hash/9a6f6e0d6781d1cb8689192408946d73-Abstract-Conference.html) obtained empirical privacy lower bounds from one training run by independently randomizing the inclusion of multiple canaries.

The correct assurance pattern is therefore two-sided:

- a provenance-bound accountant or theorem provides a claimed \((\epsilon, \delta)\) upper bound only for the complete mechanism and composed release portfolio;
- a preregistered adversarial audit provides an implementation-sensitive empirical lower bound under its registered game;
- a statistically valid lower bound inconsistent with the claimed \((\epsilon, \delta)\) region blocks the claim;
- failure to find such an inconsistency does not validate the accountant or expand either result beyond its protected unit, adjacency relation, interface, implementation, or validity horizon.

## Tree ensembles and XGBoost

The direct evidence base is narrower here. Yeom et al. included tree-model experiments, and Tramèr et al. showed decision-tree extraction from APIs. Differentially private GBDT construction has also been studied—for example, [Li et al. (AAAI 2020)](https://doi.org/10.1609/aaai.v34i01.5422) bound sensitivity through gradient and leaf-value controls and allocated privacy budget across trees. None of these papers establishes that an ordinary, non-private, current XGBoost artifact is safe after one reference-loss attack fails.

The release mode changes the threat. A distributed UBJ bundle already reveals the ensemble to the recipient, so API model theft is no longer the principal confidentiality question. Membership, attribute, property, and reconstruction leakage remain relevant. An API deployment additionally exposes a configurable channel: labels, probabilities, margins, SHAP values, leaf indices, per-tree contributions, batch behavior, missing/partial inputs, explanations, rate limits, and query budgets. Explanation endpoints deserve separate scrutiny because explanations can materially accelerate reconstruction in other model classes ([Milli et al., ACM FAT* 2019](https://doi.org/10.1145/3287560.3287562)); transfer of that result to TreeSHAP must be tested rather than assumed.

For the repository's XGBoost worker, the literature supports these labels and next steps:

- call the implemented procedure a **reference-loss membership screen**;
- retain `floor`/`screen` semantics and `can_clear: false`;
- add deployment-prior PPV, per-record/tail summaries, and reference-data mismatch sensitivity;
- add stronger multi-reference likelihood-ratio attacks before claiming LiRA coverage;
- create separate label-only, score-API, explanation-API, and full-artifact profiles;
- refuse very-low-FPR claims when the nonmember sample is too small for a useful conservative bound;
- treat transfer from neural or single-tree studies to boosted ensembles as an explicit evidence limitation.

## LLM memorization, extraction, and canary testing

### Three complementary audit and probe modes

The literature motivates three distinct designs, only the first two of which necessarily use inserted canaries:

| Canary mode | Primary question | Valid result | Main limitation |
|---|---|---|---|
| Rank/exposure canary | Does an inserted random secret receive an unusually favorable (low numerical) perplexity rank within a declared randomness space? | Memorization/exposure diagnostic under a fixed randomness space and scoring interface; an extraction floor only when a registered extraction algorithm succeeds through the claimed release interface | Requires a declared randomness space and full-enough scoring to estimate rank |
| Randomized IN/OUT canary | Can an auditor distinguish independently included canaries from excluded controls? | Confidence-qualified empirical privacy lower bound under the registered independent inclusion randomization, scoring rule, and observation model | Requires intervention before training and blinded inclusion ground truth |
| Naturalistic extraction probe | Can the actual recipient elicit domain-realistic or PII-shaped content? | Recipient-realizable extraction/reconstruction floor | Harder to control, may be contaminated, and does not estimate population prevalence |

Randomized IN/OUT designs must state their assignment mechanism exactly. The version 1.1 profile uses complete randomization with fixed member/nonmember arm sizes, so its assignments are dependent; a Bernoulli design with independent inclusion bits would instead preregister an inclusion probability and report realized arm counts.

[Carlini et al. (USENIX Security 2019)](https://www.usenix.org/conference/usenixsecurity19/presentation/carlini) introduced the exposure measure for a canary \(s\) instantiated from a declared randomness space \(R\):

```text
exposure_R(s) = log2(|R|) - log2(rank_R(s))
```

The format, random space, tokenizer, insertion count, scoring rule, tie handling, and rank estimator define the quantity. A rank is exact only if every candidate in the registered space is scored, or an exact ranking procedure with proven completeness is used. Sampled or fitted tail ranks require uncertainty; top-k log probabilities generally cannot recover full-sequence rank.

The practical risk is not merely theoretical. [Carlini et al. (USENIX Security 2021)](https://www.usenix.org/conference/usenixsecurity21/presentation/carlini-extracting) recovered verbatim GPT-2 training sequences through generate-then-rank attacks. [Carlini et al. (ICLR 2023)](https://openreview.net/forum?id=TatRHT_1cK) found memorization increased with capacity, duplication, and prompt-context length within the studied settings. [Kandpal et al. (ICML 2022)](https://proceedings.mlr.press/v162/kandpal22a.html) found regeneration strongly associated with duplication and showed that deduplication reduced the evaluated attacks, but did not create a privacy guarantee.

Canary construction must match the released channel. [Meeus et al. (ICML 2025)](https://proceedings.mlr.press/v267/meeus25a.html) found that canaries effective against a model can be poor auditors when only synthetic data is released; canaries with an in-distribution prefix and high-perplexity suffix better matched that channel. This argues for a channel-specific canary protocol rather than one universal string format.

### Why null LLM attacks are especially weak evidence

LLM membership results are mixed, not contradictory, because the games differ. [Mattern et al. (Findings of ACL 2023)](https://aclanthology.org/2023.findings-acl.719/) showed that reference-model attacks are fragile to reference-distribution mismatch and proposed neighbourhood calibration. [Duan et al. (COLM 2024)](https://openreview.net/forum?id=av0D19pSkU) found several pretraining MIAs near random in Pythia/Pile settings and traced apparent successes to temporal or distribution shifts and fuzzy membership boundaries. [Meeus et al. (USENIX Security 2024)](https://www.usenix.org/conference/usenixsecurity24/presentation/meeus) studied a different, document-level game. These studies collectively require matched time, domain, length, duplication, and style controls—not a conclusion that LLM membership is either universally easy or universally impossible.

Aligned chat interfaces also do not erase the question. [Nasr et al. (ICLR 2025)](https://openreview.net/forum?id=vjel3nWP2a) demonstrated scalable extraction attacks against aligned production language models under their tested conditions. Evidence must therefore bind the deployed endpoint, system formatting, filters, refusals, model revision, rate limits, time window, and full query ledger—not only an unaligned checkpoint.

For MRA, every applicable experimental dimension—such as insertion count, prefix, prompt template, checkpoint, decoder, retry policy, score threshold, and abstention rule—should be preregistered for the relevant canary mode; inapplicable dimensions must not be silently imported across modes. For randomized IN/OUT audits, the inclusion vector should be sampled and committed before training, withheld from the scoring procedure until scores and guesses are frozen, and revealed only for evaluation. Repeated prompts for one canary are clustered observations. All attempted tests must be retained, and simultaneous error control must cover post-selection. White-box logits or training updates are valuable implementation diagnostics but cannot be relabelled as recipient-realizable evidence when the production interface exposes text only.

## LLM output watermarking

### What watermark schemes establish

[Kirchenbauer et al. (ICML 2023)](https://proceedings.mlr.press/v202/kirchenbauer23a.html) introduced a soft green-list watermark with a one-sided detection statistic. Subsequent work explored different trade-offs: distribution preservation up to a declared maximum generation budget in [Kuditipudi et al. (TMLR 2024)](https://openreview.net/forum?id=FpaCL1M02C); unbiasedness under the construction's stated random-key quantifier in [Hu et al. (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/c5b00c5bdcc6fe35907dbcca03d27652-Abstract-Conference.html); and cryptographic undetectability to parties without the secret key, assuming one-way functions and sufficient generation entropy, in [Christ, Gunn, and Zamir (COLT 2024)](https://proceedings.mlr.press/v247/christ24a.html). These properties have different quantifiers and threat models. Labels such as “unbiased,” “distortion-free,” “robust,” or “undetectable” are not interchangeable evidence fields.

A valid detector result must bind the exact scheme, tokenizer, canonicalization, context/hash rule, key version, generation parameters, score statistic, threshold, and eligible-token rule. A positive result means only that the configured test rejected its registered no-watermark null for the observed text at its calibrated decision threshold. It does not, without an authenticated link, establish provider identity, model identity, user identity, or authorship.

### Calibration and multiplicity

[Fernandez et al. (IEEE WIFS 2023)](https://doi.org/10.1109/WIFS58808.2023.10374576) found severe empirical miscalibration of nominal z-test false-positive rates and identified repeated token contexts—and the resulting dependence in token scores—as one important cause. This is directly relevant to audit design. Evidence should retain both total and unique scored contexts, deduplicate or explicitly model repeated contexts, and validate the detector tail on large, domain- and language-matched negative corpora.

The complete hypothesis family includes every key, scheme, tokenizer, language, prompt stratum, normalization, transformation, document window, and alignment offset searched or selected after seeing the data, plus any threshold chosen post hoc. Sliding-window or best-span detection selects a statistic after many searches. The release decision must use a preregistered familywise procedure or a globally calibrated maximum statistic, not the smallest unadjusted p-value.

Power must be reported as a curve over output length, entropy, domain, language, and operational FPR. [Kirchenbauer et al. (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/d78e9e4316e1714fbb0f20be66f8044c-Abstract-Conference.html) found meaningful survival under studied human and machine paraphrases. In Kuditipudi et al.'s Alpaca-7B instruction-following case study, only about 25% of responses—whose median length was about 100 tokens—were detectable at \(p \le 0.01\); that result should not be generalized beyond the studied model and setting. Neither paper supports a universal minimum-token or robustness claim.

### Adaptive removal and spoofing

Passive paraphrase is weaker than an attacker who learns the marking rule. [Zhang et al. (ICML 2024)](https://proceedings.mlr.press/v235/zhang24o.html) proved strong watermarking impossible under a threat model in which the attacker has a quality oracle and a perturbation oracle that preserves quality with nontrivial probability and induces an efficiently mixing random walk over high-quality outputs; they also instantiated the attack against three studied schemes. [Jovanović et al. (ICML 2024)](https://proceedings.mlr.press/v235/jovanovic24a.html) demonstrated black-box watermark stealing followed by scrubbing and spoofing against studied schemes. [Gu et al. (ICLR 2024)](https://proceedings.iclr.cc/paper_files/paper/2024/hash/a86d17b6cd70366d56ab48d2a05a4df1-Abstract-Conference.html) showed that watermark behavior can be distilled into another model. [Pang et al. (NeurIPS 2024)](https://proceedings.neurips.cc/paper_files/paper/2024/hash/fa86a9c7b9f341716ccb679d1aeb9afa-Abstract-Conference.html) documented trade-offs involving multiple keys and detector APIs. [Rastogi and Pruthi (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.1005/) strengthened paraphrase attacks after learning green-list behavior.

More recent evaluations reinforce the need for attack diversity: [Liang et al. (Findings of EMNLP 2025)](https://aclanthology.org/2025.findings-emnlp.1148/) compared multiple watermark and attack families; [Chen et al. (ICML 2025)](https://proceedings.mlr.press/v267/chen25bq.html) targeted n-gram watermark removal; and [An et al. (EACL 2026)](https://aclanthology.org/2026.eacl-long.229/) demonstrated watermark spoofing through knowledge distillation. These are scheme- and setting-specific results, not universal impossibility proofs, but they rule out treating a single positive detector result as authenticated provenance.

An audit-grade watermark study therefore needs:

- empirical null calibration, including repetitive text, code, multilingual text, and domain subgroups;
- simultaneous false-positive control over the entire search family;
- power and quality curves rather than one headline detection rate;
- blind edits, paraphrase, translation, truncation, and mixed human/model text;
- adaptive rule recovery, informed paraphrase, distillation, scrubbing, spoofing, multi-key, and detector-oracle attacks;
- explicit key custody, rotation, compromise, rate-limit, and detector-output policies;
- a narrow claim: key-associated statistical signal, with `can_clear: false`.

Signed generation logs or content credentials can provide a separate authenticated provenance link, but they are a separate cryptographic system with their own key, identity, replay, and integrity assumptions. Watermark detection should corroborate such a system, not silently replace it.

## Evidence semantics for MRA

| Evidence | What it may establish | What it must not establish | MRA treatment |
|---|---|---|---|
| Successful membership or extraction attack | Leakage under the bound game and interface | Population-wide prevalence or a universal privacy value | `floor`; may block; never clear |
| Failed empirical attack | This attack failed under this data, power, and budget | Absence of leakage | `screen`; inconclusive |
| Complete, replayed DP accountant | A formal ceiling under exact scope and composition | Safety of excluded pipeline stages or releases | `ceiling`; may clear only if provenance and scope are complete |
| Randomized IN/OUT canary audit | Empirical lower bound for the registered training algorithm | A formal upper bound or arbitrary-record safety | `floor` or `screen` |
| Exact canary extraction through the bound recipient interface | Recipient-realizable extraction floor under the registered prompts, decoding, side information, and query budget | General leakage prevalence | `floor`; may block |
| Rank exposure from auditor-only logits | Model memorization diagnostic | Recipient-realizable black-box leakage | auditor-only `floor`/`screen` |
| Watermark detector hit | Rejection of the registered no-watermark null for a declared key-associated detector at its calibrated threshold | Authorship, provider identity, or privacy | provenance screen/floor only |
| Watermark detector miss | Failure to reject the registered null under the tested text length, entropy, transformations, and detector power | Human authorship or non-generation | `screen`; inconclusive |
| Model extraction | Model confidentiality/fidelity loss | Training-record membership by itself | separate extraction threat |

## Framework gap analysis and recommendations

| Literature-derived requirement | Repository status after this customization | Recommended action |
|---|---|---|
| Explicit game, interface, population, and adversary assumptions | Core analyzer inputs now carry a verified source-observed release/policy/artifact/interface/population/game context; XGBoost separately binds its worker game | Require future family-specific workers to populate the same envelope plus their modality-specific partitions/transcripts |
| Attack evidence is one-sided | Implemented as floor/screen semantics | Preserve `can_clear: false` for XGBoost, canary, and watermark experiments |
| Low-FPR simultaneous inference | Core and XGBoost now divide alpha across TPR/FPR bounds and declared comparisons | Retain tail-sample refusal; future subgroup and LLM families need dedicated contracts |
| Realistic membership priors and tail heterogeneity | XGBoost now emits preregistered-prior PPV plus descriptive class/score tails | Add preregistered, adequately powered subgroup families before inferential tail claims |
| Strong, varied membership attacks | Reference-loss screen only | Add multi-reference LiRA-style, reference-mismatch, label-only, and full-artifact profiles |
| Formal DP plus implementation audit | Core has source-bound accountant and attack paths; 0.7.0 also binds the finite-secret prior-mass cap and pairwise-DP premise | Add independently operated accountant replay and randomized-canary replay tests |
| Three distinct canary modes | Separated in the lintable profile; no evidence analyzer exists | Version separate exposure, randomized IN/OUT, and naturalistic extraction schemas/workers |
| Watermark null calibration and adaptive attack suite | Required by profile 1.1 and its linter; no detector/attack worker exists | Implement replayable scoring, calibration, quality, power, and attack-matrix evidence |
| Complete interactive transcript assurance | Explicitly refused by optimizer | Retain refusal until a versioned transcript/channel analyzer exists |
| Portfolio/lifetime composition | Present for finite mechanisms, not a complete LLM service | Bind updates, memory, RAG, tools, concurrent sessions, retention, and all related releases |

Version 0.6 resolves the audit's critical evidence-rebinding defect with a source-observed context checked before analysis. The next priority is trustworthy family-specific collection: a cryptographically bound envelope cannot make an incomplete or methodologically invalid experiment true.

## Research gaps relevant to the roadmap

- Direct, independently replicated privacy attacks and upper-bound mechanisms for current XGBoost/GBDT release formats remain sparse relative to neural-model literature.
- Very-low-FPR evaluation often lacks enough independent nonmembers, especially for small protected populations and subgroup tails.
- Transfer from synthetic canary behavior to real-record privacy is not identified; canaries are diagnostics, not population estimators.
- Pretraining membership for LLMs remains sensitive to label quality, near duplication, temporal shift, and unknown training mixtures.
- Watermark deployment evidence is limited for multilingual, low-entropy, code, long-lived multi-key, and adversarial detector-API settings.
- No reviewed study supplies a complete clearance theorem for an evolving LLM service with RAG, tools, memory, filters, retention, updates, and concurrent adaptive users.
- Dependence across multiple models, releases, summaries, and interactive observations remains a central composition problem; testing each release independently is insufficient.

## Curated source list

### Privacy games, membership, extraction, and DP

- Blackwell. [Equivalent Comparisons of Experiments](https://doi.org/10.1214/aoms/1177729032). *Annals of Mathematical Statistics*, 1953.
- Dwork, McSherry, Nissim, Smith. [Calibrating Noise to Sensitivity in Private Data Analysis](https://doi.org/10.1007/11681878_14). TCC 2006.
- Kairouz, Oh, Viswanath. [The Composition Theorem for Differential Privacy](https://proceedings.mlr.press/v37/kairouz15.html). ICML 2015.
- Tramèr et al. [Stealing Machine Learning Models via Prediction APIs](https://www.usenix.org/conference/usenixsecurity16/technical-sessions/presentation/tramer). USENIX Security 2016.
- Shokri et al. [Membership Inference Attacks Against Machine Learning Models](https://www.ieee-security.org/TC/SP2017/papers/313.pdf). IEEE S&P 2017. DOI: [10.1109/SP.2017.41](https://doi.org/10.1109/SP.2017.41).
- Yeom et al. [Privacy Risk in Machine Learning: Analyzing the Connection to Overfitting](https://doi.org/10.1109/CSF.2018.00027). IEEE CSF 2018.
- Salem et al. [*ML-Leaks: Model and Data Independent Membership Inference Attacks and Defenses on Machine Learning Models*](https://doi.org/10.14722/ndss.2019.23119). NDSS 2019.
- Milli et al. [Model Reconstruction from Model Explanations](https://doi.org/10.1145/3287560.3287562). ACM FAT* 2019.
- Nasr, Shokri, Houmansadr. [Comprehensive Privacy Analysis of Deep Learning: Passive and Active White-box Inference Attacks against Centralized and Federated Learning](https://doi.org/10.1109/SP.2019.00065). IEEE S&P 2019.
- Li et al. [Privacy-Preserving Gradient Boosting Decision Trees](https://doi.org/10.1609/aaai.v34i01.5422). AAAI 2020.
- Jagielski et al. [High Accuracy and High Fidelity Extraction of Neural Networks](https://www.usenix.org/conference/usenixsecurity20/presentation/jagielski). USENIX Security 2020.
- Leino and Fredrikson. [Stolen Memories: Leveraging Model Memorization for Calibrated White-Box Membership Inference](https://www.usenix.org/conference/usenixsecurity20/presentation/leino). USENIX Security 2020.
- Jayaraman et al. [Revisiting Membership Inference Under Realistic Assumptions](https://petsymposium.org/popets/2021/popets-2021-0031.php). PoPETs 2021.
- Song and Mittal. [Systematic Evaluation of Privacy Risks of Machine Learning Models](https://www.usenix.org/conference/usenixsecurity21/presentation/song). USENIX Security 2021.
- Carlini et al. [Membership Inference Attacks From First Principles](https://doi.org/10.1109/SP46214.2022.9833649). IEEE S&P 2022.
- Ye et al. [Enhanced Membership Inference Attacks against Machine Learning Models](https://doi.org/10.1145/3548606.3560675). ACM CCS 2022.
- Salem et al. [SoK: Let the Privacy Games Begin!](https://www.microsoft.com/en-us/research/publication/sok-let-the-privacy-games-begin-a-unified-treatment-of-data-inference-privacy-in-machine-learning/). IEEE S&P 2023.
- Nasr et al. [Tight Auditing of Differentially Private Machine Learning](https://www.usenix.org/conference/usenixsecurity23/presentation/nasr). USENIX Security 2023.
- Steinke, Nasr, Jagielski. [Privacy Auditing with One (1) Training Run](https://proceedings.neurips.cc/paper_files/paper/2023/hash/9a6f6e0d6781d1cb8689192408946d73-Abstract-Conference.html). NeurIPS 2023.

### LLM memorization, canaries, and extraction

- Carlini et al. [*The Secret Sharer: Evaluating and Testing Unintended Memorization in Neural Networks*](https://www.usenix.org/conference/usenixsecurity19/presentation/carlini). USENIX Security 2019.
- Carlini et al. [Extracting Training Data from Large Language Models](https://www.usenix.org/conference/usenixsecurity21/presentation/carlini-extracting). USENIX Security 2021.
- Kandpal, Wallace, Raffel. [Deduplicating Training Data Mitigates Privacy Risks in Language Models](https://proceedings.mlr.press/v162/kandpal22a.html). ICML 2022.
- Carlini et al. [Quantifying Memorization Across Neural Language Models](https://openreview.net/forum?id=TatRHT_1cK). ICLR 2023.
- Mattern et al. [Membership Inference Attacks against Language Models via Neighbourhood Comparison](https://aclanthology.org/2023.findings-acl.719/). Findings of ACL 2023.
- Lukas et al. [Analyzing Leakage of Personally Identifiable Information in Language Models](https://doi.org/10.1109/SP46215.2023.00154). IEEE S&P 2023.
- Duan et al. [Do Membership Inference Attacks Work on Large Language Models?](https://openreview.net/forum?id=av0D19pSkU). COLM 2024.
- Meeus et al. [Did the Neurons Read your Book?](https://www.usenix.org/conference/usenixsecurity24/presentation/meeus). USENIX Security 2024.
- Nasr et al. [Scalable Extraction of Training Data from Aligned, Production Language Models](https://openreview.net/forum?id=vjel3nWP2a). ICLR 2025.
- Meeus et al. [The Canary's Echo](https://proceedings.mlr.press/v267/meeus25a.html). ICML 2025.

### LLM watermarking

- Kirchenbauer et al. [A Watermark for Large Language Models](https://proceedings.mlr.press/v202/kirchenbauer23a.html). ICML 2023.
- Fernandez et al. [Three Bricks to Consolidate Watermarks for Large Language Models](https://doi.org/10.1109/WIFS58808.2023.10374576). IEEE WIFS 2023.
- Kirchenbauer et al. [On the Reliability of Watermarks for Large Language Models](https://proceedings.iclr.cc/paper_files/paper/2024/hash/d78e9e4316e1714fbb0f20be66f8044c-Abstract-Conference.html). ICLR 2024.
- Hu et al. [Unbiased Watermark for Large Language Models](https://proceedings.iclr.cc/paper_files/paper/2024/hash/c5b00c5bdcc6fe35907dbcca03d27652-Abstract-Conference.html). ICLR 2024.
- Kuditipudi et al. [Robust Distortion-free Watermarks for Language Models](https://openreview.net/forum?id=FpaCL1M02C). TMLR 2024.
- Christ, Gunn, Zamir. [Undetectable Watermarks for Language Models](https://proceedings.mlr.press/v247/christ24a.html). COLT 2024.
- Zhao et al. [Provable Robust Watermarking for AI-Generated Text](https://proceedings.iclr.cc/paper_files/paper/2024/hash/beae9ed5316bcc48e616754c06c11875-Abstract-Conference.html). ICLR 2024.
- Zhang et al. [Watermarks in the Sand](https://proceedings.mlr.press/v235/zhang24o.html). ICML 2024.
- Jovanović, Staab, Vechev. [Watermark Stealing in Large Language Models](https://proceedings.mlr.press/v235/jovanovic24a.html). ICML 2024.
- Gu et al. [On the Learnability of Watermarks for Language Models](https://proceedings.iclr.cc/paper_files/paper/2024/hash/a86d17b6cd70366d56ab48d2a05a4df1-Abstract-Conference.html). ICLR 2024.
- Pang et al. [No Free Lunch in LLM Watermarking](https://proceedings.neurips.cc/paper_files/paper/2024/hash/fa86a9c7b9f341716ccb679d1aeb9afa-Abstract-Conference.html). NeurIPS 2024.
- Rastogi and Pruthi. [Revisiting the Robustness of Watermarking to Paraphrasing Attacks](https://aclanthology.org/2024.emnlp-main.1005/). EMNLP 2024.
- Liang et al. [Watermark under Fire](https://aclanthology.org/2025.findings-emnlp.1148/). Findings of EMNLP 2025.
- Chen et al. [De-mark](https://proceedings.mlr.press/v267/chen25bq.html). ICML 2025.
- An et al. [DITTO](https://aclanthology.org/2026.eacl-long.229/). EACL 2026.

### Authoritative standards and guidance

- NIST. [Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations, AI 100-2e2025](https://csrc.nist.gov/pubs/ai/100/2/e2025/final).
- NIST. [Guidelines for Evaluating Differential Privacy Guarantees, SP 800-226](https://csrc.nist.gov/pubs/sp/800/226/final).
- NIST. [Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile, AI 600-1](https://doi.org/10.6028/NIST.AI.600-1).
