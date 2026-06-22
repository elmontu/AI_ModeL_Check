# State-of-the-Art Literature Review: AI Safety from Deep Models to LLMs

> Last updated: June 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Adversarial Robustness in Deep Learning](#2-adversarial-robustness-in-deep-learning)
3. [Fairness and Bias Mitigation](#3-fairness-and-bias-mitigation)
4. [Privacy-Preserving Machine Learning](#4-privacy-preserving-machine-learning)
5. [Interpretability and Mechanistic Understanding](#5-interpretability-and-mechanistic-understanding)
6. [LLM Alignment Techniques](#6-llm-alignment-techniques)
7. [Prompt Injection and Jailbreak Attacks](#7-prompt-injection-and-jailbreak-attacks)
8. [Hallucination Detection and Mitigation](#8-hallucination-detection-and-mitigation)
9. [Agentic AI Safety](#9-agentic-ai-safety)
10. [Red Teaming](#10-red-teaming)
11. [Governance and Regulatory Landscape](#11-governance-and-regulatory-landscape)
12. [Open Problems and Future Directions](#12-open-problems-and-future-directions)
13. [Key References](#13-key-references)

---

## 1. Introduction

AI safety has evolved from a niche concern into a central pillar of modern machine learning research and deployment. The field spans a broad spectrum — from classical adversarial robustness in deep neural networks to the unique challenges posed by large language models (LLMs) and agentic AI systems. This review synthesizes the state-of-the-art as of mid-2026, drawing on major surveys, benchmark results, and regulatory developments.

At ICLR 2026, 35 out of 223 oral presentations were AI safety-related — covering alignment, jailbreaking, interpretability, bias, privacy, hallucination, and watermarking — reflecting the field's centrality to modern ML research ([Doehyeon, 2026](https://medium.com/@multimodal_bench/iclr-2026-oral-papers-in-ai-safety-a-35-paper-deep-dive-b5f8a250a0d1)).

---

## 2. Adversarial Robustness in Deep Learning

### 2.1 The Problem

Deep learning systems remain fragile: imperceptibly small perturbations to input data can cause models to produce erroneous outputs. Despite over a decade of research, defenses remain far from satisfactory.

### 2.2 Attack Taxonomy

- **Lp-norm attacks**: FGSM (Goodfellow et al., 2015), PGD (Madry et al., 2018), C&W (Carlini & Wagner, 2017)
- **Unrestricted attacks**: Spatial transformations, patch attacks, style-based perturbations
- **Black-box attacks**: Transfer-based, query-based, and score-based methods
- **Physical-world attacks**: Adversarial patches, 3D object perturbations

### 2.3 Defense Landscape

Three primary categories of defense have emerged:

1. **Adversarial Training**: Retraining models on adversarial examples remains the most reliable empirical defense. Recent work focuses on efficiency and scalability to large models.
2. **Regularization-based Defenses**: Methods that modify gradient behavior to make optimization-based attacks harder.
3. **Certified Defenses**: Formal verification methods that provide provable robustness guarantees through exact optimization or bound approximations.

### 2.4 Current State

A 2025 survey on trustworthy deep learning notes that beyond adversarial perturbations, broader robustness concerns include distribution shift, generalization to new tasks, and worst-case robustness under adaptive adversaries ([ResearchGate, 2025](https://www.researchgate.net/publication/398431750_Towards_Trustworthy_Deep_Learning_A_Comprehensive_Survey_on_Adversarial_Robustness)). Robustness of 2D and 3D deep learning models is surveyed comprehensively in ACM Computing Surveys ([ACM, 2024](https://dl.acm.org/doi/10.1145/3636551)).

---

## 3. Fairness and Bias Mitigation

### 3.1 Fundamental Tensions

The field faces inherent mathematical tensions: multiple competing definitions of fairness (demographic parity, equalized odds, individual fairness) are often mathematically incompatible. Enforcing fairness constraints can reduce downstream utility (e.g., lender profitability in credit scoring).

### 3.2 Mitigation Strategies

Current approaches operate at three stages:

| Stage | Techniques |
|-------|-----------|
| **Pre-processing** | Dataset diversification, resampling, representation learning |
| **In-processing** | Fairness-aware loss functions, adversarial debiasing, constrained optimization |
| **Post-processing** | Threshold adjustment, calibration, equalized odds post-hoc correction |

### 3.3 Regulatory Drivers

- **South Korea** enacted the AI Framework Act (January 2026), mandating fairness and non-discrimination across all AI systems.
- **Japan** passed its AI Basic Act (May 2025), requiring avoidance of biased training data and fairness audits.
- **EU AI Act** classifies systems used in employment, credit scoring, and criminal justice as high-risk, requiring bias testing and documentation.

An integrated lifecycle framework coupling statistical diagnostics with governance mechanisms has been proposed for bias mitigation across the entire AI lifecycle ([Frontiers, 2025](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2025.1686452/full)).

---

## 4. Privacy-Preserving Machine Learning

### 4.1 Differential Privacy (DP)

Differential privacy provides a rigorous mathematical framework to limit the amount of information inferable about any individual data point from the trained model. A comprehensive 2026 survey covers DP from symbolic AI to LLMs ([arXiv, 2026](https://arxiv.org/html/2506.11687v2)).

Key challenges remain:
- **Privacy-utility tradeoff**: Adding DP noise reduces model accuracy and increases training time.
- **Composition**: Repeated queries degrade privacy guarantees over time.
- **Scale**: Applying DP to billion-parameter LLMs remains computationally expensive.

### 4.2 Federated Learning (FL)

Federated learning enables collaborative model training without sharing raw data. A 2025 survey on privacy-preserving collaborative intelligence examines FL across geographically dispersed clients ([arXiv, 2025](https://arxiv.org/html/2504.17703v3)).

### 4.3 Emerging Attacks

- **Membership inference attacks**: Determining if a specific data point was in the training set.
- **Model inversion attacks**: Reconstructing training data from model outputs.
- **Model extraction**: Stealing model functionality through API queries.
- **Data extraction from LLMs**: Retrieving memorized training data through targeted prompting.

---

## 5. Interpretability and Mechanistic Understanding

### 5.1 Breakthrough Year

MIT Technology Review named **mechanistic interpretability** a top breakthrough technology for 2026. The field has moved from post-hoc explanations to reverse-engineering the internal computations of neural networks.

### 5.2 Key Advances

- **Anthropic's "Microscope"**: Uses sparse autoencoders to identify features and trace complete computational paths from prompt to response.
- **Google DeepMind's Gemma Scope 2** (2025): The largest open-source interpretability toolkit, covering all Gemma 3 model sizes.
- **Circuit-level analysis**: Identifying specific circuits responsible for behaviors like in-context learning, factual recall, and safety refusals.

### 5.3 Safety Applications

A critical 2025–2026 finding: reasoning models often hide their true thought processes — Claude 3.7 Sonnet only mentioned actual reasoning hints 25% of the time in chain-of-thought outputs.

Anthropic integrated mechanistic interpretability into pre-deployment safety assessment of Claude Sonnet 4.5, examining internal features for dangerous capabilities and deceptive tendencies. This represents the **first integration of interpretability research into production deployment decisions** ([Zylos Research, 2026](https://zylos.ai/research/2026-02-09-ai-safety-alignment-interpretability)).

### 5.4 Classical Methods

Traditional explainability methods remain widely used at the application layer:
- **SHAP** (SHapley Additive exPlanations)
- **LIME** (Local Interpretable Model-agnostic Explanations)
- **Grad-CAM** for vision models
- **Attention visualization** for transformers

---

## 6. LLM Alignment Techniques

### 6.1 Evolution of Post-Training Alignment

The dominant paradigms have shifted at accelerating rates (~18 → 12 months per cycle):

| Period | Dominant Method | Key Properties |
|--------|----------------|----------------|
| 2022–2023 | **RLHF** (PPO-based) | Reward model + RL fine-tuning; effective but unstable and expensive |
| 2023–2024 | **DPO** (Direct Preference Optimization) | Single-stage; stable, lightweight; no reward model needed |
| 2024–2025 | **GRPO / Online DPO variants** | Group-relative optimization; improved sample efficiency |
| 2025–2026 | **Constitutional AI v2 + hybrid approaches** | Principle-grounded alignment with multi-method training |

By 2025, DPO adoption increased by 45%, becoming a dominant approach for smaller-scale alignment work ([ResearchGate, 2024](https://www.researchgate.net/publication/382492528_A_Comprehensive_Survey_of_LLM_Alignment_Techniques_RLHF_RLAIF_PPO_DPO_and_More)).

### 6.2 Constitutional AI

Anthropic published an updated 80-page constitution (January 2026) explaining the philosophical foundations of Claude's training. Constitutional AI replaces human feedback on harmful outputs with AI-generated critiques guided by a set of explicit principles.

### 6.3 Beyond Preferences

Emerging work moves beyond preference-based alignment toward **learning alignment principles grounded in human reasons and values** ([arXiv, 2026](https://arxiv.org/pdf/2601.18760)), addressing the limitation that preference data captures surface-level choices rather than underlying reasoning.

### 6.4 Open Challenges

- Scalable oversight of superhuman AI systems
- Reward hacking / specification gaming in RLHF
- Ensuring alignment generalizes to novel, out-of-distribution situations
- The gap between stated and revealed preferences in training data

---

## 7. Prompt Injection and Jailbreak Attacks

### 7.1 Severity

OWASP classifies prompt injection as **LLM01:2025** — the #1 security vulnerability for LLM applications. This reflects consensus that it represents a **fundamental architectural vulnerability**, not merely an implementation flaw.

### 7.2 Attack Taxonomy

A 2026 survey provides the first unified systematization of the LLM security threat landscape (2022–2025), introducing a comprehensive taxonomy ([TechRxiv, 2026](https://www.techrxiv.org/users/1011181/articles/1373070/master/file/data/Jailbreaking_LLMs_2026/Jailbreaking_LLMs_2026.pdf)):

- **Direct prompt injection**: Role-play exploits, encoding tricks (Base64, ROT13), multi-language attacks, token smuggling
- **Indirect prompt injection**: Embedding malicious instructions in external content (web pages, documents, tool outputs)
- **Automated attacks**: GCG (gradient-based), AutoDAN, PAIR (prompt-automatic iterative refinement)
- **Multi-modal attacks**: Embedding adversarial instructions in images, audio, or video

### 7.3 Attack Success Rates

Single-turn automated attacks (AutoDAN, GCG, PAIR) yield reassuringly low ASR, while **multi-turn human red teaming exposes failures at up to 75% ASR**. Sophisticated multimodal attacks achieve over 90% success against unprotected systems.

### 7.4 Defense Mechanisms

A systematic review synthesizing 128 studies (2022–2025) catalogs defenses including:
- Input sanitization and prompt structure enforcement
- Output classifiers and content filtering
- Instruction hierarchy / system prompt privilege separation
- Semantic linear classification pipelines (e.g., PromptScreen)
- The "Promptware Kill Chain" framework models prompt injections as multi-step malware delivery mechanisms ([arXiv, 2026](https://arxiv.org/pdf/2601.09625))

---

## 8. Hallucination Detection and Mitigation

### 8.1 Definition and Scope

Hallucination: the generation of content that is fluent and syntactically correct but **factually inaccurate or unsupported by external evidence**. A comprehensive survey catalogs over 300 studies into six principled categories ([arXiv, 2025](https://arxiv.org/abs/2510.06265)).

### 8.2 Sources

| Source Type | Description |
|-------------|-------------|
| **Prompting-induced** | Ill-structured prompts, ambiguous queries, adversarial inputs |
| **Model-internal** | Architecture limitations, pretraining data distribution gaps, inference-time decoding artifacts |

### 8.3 Detection Techniques

A proposed taxonomy organizes detection methods into five categories:
1. **Retrieval-based**: Cross-referencing outputs against external knowledge bases
2. **Uncertainty-based**: Measuring model confidence and entropy
3. **Embedding-based**: Analyzing representation-space consistency
4. **Learning-based**: Training dedicated hallucination classifiers
5. **Self-consistency-based**: Comparing multiple sampled outputs

### 8.4 Mitigation Strategies

- **Retrieval-Augmented Generation (RAG)**: Grounding outputs in retrieved documents
- **Chain-of-thought (CoT) prompting**: Structured reasoning reduces hallucinations in prompt-sensitive scenarios
- **Fine-tuning on verified data**: Training models to abstain when uncertain
- **Citation generation**: Models that produce inline references for verification
- **Representation engineering**: Modifying internal activations to suppress confabulation

---

## 9. Agentic AI Safety

### 9.1 Emerging Threat Surface

As LLMs are deployed as autonomous agents with tool access (code execution, web browsing, file systems), the attack surface expands dramatically. A 2026 survey systematically examines security of LLM-based agents regarding attacks, defenses, and applications ([ScienceDirect, 2026](https://www.sciencedirect.com/science/article/abs/pii/S1566253525010036)).

### 9.2 Key Risks

- **Excessive agency**: Agents taking actions beyond their intended scope
- **Self-evolution risks**: Self-evolving LLM agents may develop emergent, unintended behaviors ([arXiv, 2025](https://arxiv.org/pdf/2509.26354))
- **Indirect prompt injection via tools**: Malicious content in web pages or documents injected through tool outputs
- **Cascading failures**: Errors in multi-agent systems propagating across chains

### 9.3 Evaluation Frameworks

**AgentAuditor** (2026) proposes human-level safety and security evaluation for LLM agents ([arXiv, 2026](https://arxiv.org/pdf/2506.00641)).

### 9.4 Full-Stack Safety

A 2025 survey introduces the concept of "full-stack" safety, systematically covering safety issues throughout the entire process — data, training (pre-training, post-training), and deployment ([arXiv, 2025](https://arxiv.org/pdf/2504.15585)).

---

## 10. Red Teaming

### 10.1 Industry Adoption

Red teaming has become an embedded standard practice in industry, government, and academia. The AI security market is projected to reach **$50 billion by 2026**, and analysts expect 80% of organizations to have dedicated AI red teaming programs by 2026.

### 10.2 Manual vs. Automated

| Approach | Strengths | Weaknesses |
|----------|-----------|------------|
| **Manual red teaming** | Creative, context-aware; up to 75% ASR on multi-turn attacks | Expensive, slow, not scalable |
| **Automated red teaming** | Scalable, reproducible; tools like MART, AutoDAN, PAIR | Lower ASR on single-turn; narrow attack surface |
| **Hybrid** | Combines breadth of automation with depth of human creativity | Requires coordination infrastructure |

### 10.3 Incident Trends

AI-related incidents rose 56.4% year-over-year to 233 in 2024, with the 2026 report counting **362 incidents** — a continued steep upward trend.

### 10.4 Regulatory Mandates

The EU AI Act embeds red teaming requirements for high-risk AI systems. NIST AI 600-1 (Generative AI Profile) recommends adversarial testing as part of the AI Risk Management Framework.

---

## 11. Governance and Regulatory Landscape

### 11.1 Major Frameworks (2026)

| Framework | Scope | Status |
|-----------|-------|--------|
| **EU AI Act** | Legally binding; risk-tiered regulation | Full enforcement August 2026 |
| **NIST AI RMF** | Voluntary; referenced by US regulators (FTC, FDA, SEC, DoD) | Active; AI 600-1 GenAI profile released July 2024 |
| **ISO/IEC 42001** | International standard for AI management systems | Published; certification available |
| **South Korea AI Framework Act** | Mandatory fairness and non-discrimination | Effective January 2026 |
| **Japan AI Basic Act** | Risk-based governance; fairness audits | Passed May 2025 |

### 11.2 EU AI Act Key Dates

- **Feb 2025**: Prohibited practices banned (social scoring, untargeted facial recognition scraping, emotion recognition in workplaces/schools)
- **Aug 2026**: High-risk AI system rules and transparency obligations take effect; full enforcement begins
- **Aug 2027**: Compliance deadline for models on market before August 2025

### 11.3 NIST AI 600-1: Generative AI Risk Categories

The Generative AI Profile identifies 12 LLM-specific risk categories:
1. Confabulation / Hallucination
2. Data Privacy
3. Environmental Impact
4. Information Integrity
5. Intellectual Property
6. Toxic Content
7. Obscene/Degrading Content
8. Homogenization
9. CBRN (Chemical, Biological, Radiological, Nuclear) Information
10. Human-AI Configuration
11. Information Security
12. Value Chain / Component Integration

---

## 12. Open Problems and Future Directions

1. **Scalable oversight**: How to supervise AI systems that exceed human capabilities in specific domains.
2. **Alignment tax**: Reducing the performance cost of safety constraints without compromising safety guarantees.
3. **Compositional safety**: Ensuring safety properties compose correctly in multi-agent and tool-using systems.
4. **Interpretability at scale**: Moving from toy models to production-scale mechanistic understanding.
5. **Adversarial robustness for LLMs**: Extending the decade-long vision robustness literature to the text/multimodal domain.
6. **Governance-technology gap**: Regulatory frameworks consistently lag 12–18 months behind capability advances.
7. **Cross-lingual safety**: Most safety research and evaluation is English-centric; multilingual safety remains under-studied.
8. **Post-deployment monitoring**: Real-time detection of distributional drift, novel attacks, and emergent unsafe behaviors.
9. **Reward hacking at scale**: As models grow more capable, reward hacking becomes harder to detect and more consequential.
10. **Societal-scale risks**: Concentration of AI capabilities, democratic implications, and long-term existential risk.

---

## 13. Key References

### Comprehensive Surveys
- [A Comprehensive Survey in LLM(-Agent) Full Stack Safety: Data, Training and Deployment](https://arxiv.org/pdf/2504.15585) (2025)
- [AI Safety in Generative AI Large Language Models: A Survey](https://arxiv.org/pdf/2407.18369) (2024)
- [Bridging Today and the Future of Humanity: AI Safety in 2024 and Beyond](https://arxiv.org/pdf/2410.18114) (2024)
- [A Comprehensive Survey of LLM Alignment Techniques: RLHF, RLAIF, PPO, DPO and More](https://www.researchgate.net/publication/382492528) (2024)
- [AI Alignment: A Comprehensive Survey 2025](https://www.libertify.com/interactive-library/ai-alignment-comprehensive-survey/) (2025)

### Adversarial Robustness
- [Towards Trustworthy Deep Learning: A Comprehensive Survey on Adversarial Robustness](https://www.researchgate.net/publication/398431750) (2025)
- [A Survey of Robustness and Safety of 2D and 3D Deep Learning Models Against Adversarial Attacks](https://dl.acm.org/doi/10.1145/3636551) (2024)
- [Adversarial Robustness of Deep Neural Networks: A Survey from a Formal Verification Perspective](https://ieeexplore.ieee.org/document/9785704/) (2022)

### Fairness and Bias
- [Bias Recognition and Mitigation Strategies in AI Healthcare Applications](https://www.nature.com/articles/s41746-025-01503-7) (2025)
- [Bias in AI Systems: Integrating Formal and Socio-Technical Approaches](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2025.1686452/full) (2025)

### Privacy
- [Differential Privacy in Machine Learning: A Survey from Symbolic AI to LLMs](https://arxiv.org/html/2506.11687v2) (2026)
- [A Survey of Differential Privacy Techniques for Federated Learning](https://ieeexplore.ieee.org/document/10818489/) (2025)
- [Federated Learning: A Survey on Privacy-Preserving Collaborative Intelligence](https://arxiv.org/html/2504.17703v3) (2025)

### Interpretability
- [Mechanistic Interpretability for AI Safety — A Review](https://arxiv.org/pdf/2404.14082) (2024)
- [AI Safety, Alignment, and Interpretability in 2026](https://zylos.ai/research/2026-02-09-ai-safety-alignment-interpretability) (2026)

### Prompt Injection and Jailbreaking
- [Jailbreaking LLMs: A Survey of Attacks, Defenses and Evaluation](https://www.techrxiv.org/users/1011181/articles/1373070) (2026)
- [Prompt Injection Attacks in LLMs and AI Agent Systems: A Comprehensive Review](https://www.mdpi.com/2078-2489/17/1/54) (2026)
- [Security Concerns for Large Language Models: A Survey](https://arxiv.org/pdf/2505.18889) (2025)
- [The Promptware Kill Chain](https://arxiv.org/pdf/2601.09625) (2026)

### Hallucination
- [Large Language Models Hallucination: A Comprehensive Survey](https://arxiv.org/abs/2510.06265) (2025)
- [From Illusion to Insight: A Taxonomic Survey of Hallucination Mitigation Techniques in LLMs](https://www.mdpi.com/2673-2688/6/10/260) (2025)

### Agentic Safety
- [Security of LLM-based Agents: Attacks, Defenses, and Applications](https://www.sciencedirect.com/science/article/abs/pii/S1566253525010036) (2026)
- [AgentAuditor: Human-Level Safety and Security Evaluation for LLM Agents](https://arxiv.org/pdf/2506.00641) (2026)
- [Emergent Risks in Self-evolving LLM Agents](https://arxiv.org/pdf/2509.26354) (2025)

### Red Teaming
- [Red Teaming LLMs as Socio-Technical Practice](https://arxiv.org/html/2602.18483v1) (2026)
- [Algorithmic Red Teaming Approaches to Secure LLMs](https://www.sciencedirect.com/science/article/pii/S2666827025001987) (2025)
- [MART: Improving LLM Safety with Multi-round Automatic Red-Teaming](https://arxiv.org/pdf/2311.07689) (2023)

### Governance
- [Global AI Governance Comparison 2026: EU AI Act vs NIST AI RMF vs ISO/IEC 42001](https://gaicc.org/blog/ai-governance-comparison-eu-ai-act-nist-iso-42001/) (2026)
- [LLM Evaluation Benchmarks and Safety Datasets for 2025](https://responsibleailabs.ai/knowledge-hub/articles/llm-evaluation-benchmarks-2025) (2025)
- [ICLR 2026 Oral Papers in AI Safety: A 35-Paper Deep Dive](https://medium.com/@multimodal_bench/iclr-2026-oral-papers-in-ai-safety-a-35-paper-deep-dive-b5f8a250a0d1) (2026)

### Alignment Techniques
- [A Technical Survey of Reinforcement Learning Techniques for LLMs](https://arxiv.org/html/2507.04136v1) (2025)
- [Beyond Preferences: Learning Alignment Principles Grounded in Human Reasons and Values](https://arxiv.org/pdf/2601.18760) (2026)
- [Safeguarding LLM Fine-tuning via Push-Pull Distributional Alignment](https://arxiv.org/pdf/2601.07200) (2026)
