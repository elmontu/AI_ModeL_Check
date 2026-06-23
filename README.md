# AI Model Safety Checker

A modular Python toolkit for automated AI safety evaluation — from CNNs and tree-based models to LLMs and time-series systems. Includes 15 checker modules across 5 model-type layers, a CLI, structured JSON reports, and 200+ curated attack prompts.

```
pip install -e "."              # core only
pip install -e ".[all]"         # all optional dependencies
```

---

## Architecture

```
src/aisafety/checkers/
├── cnn/                          CNN / Vision
│   ├── adversarial.py              20 evasion attacks (FGSM → AutoAttack)
│   └── robustness.py               Corruption: noise, blur, contrast, occlusion, mCE
│
├── tree/                         Tree / Tabular
│   ├── fairness.py                 Demographic parity, equalized odds, disparate impact
│   ├── data_safety.py              PII scanning, bias detection, poisoning
│   └── interpretability.py         SHAP, LIME, feature consistency
│
├── llm/                          LLM / Transformer
│   ├── prompt_safety.py            60+ injection tests, 50+ jailbreak templates
│   ├── content_safety.py           Toxicity, hallucination, stereotypes, copyright
│   ├── guardrails.py               OWASP LLM Top 10, PII redaction, XSS
│   └── agentic_safety.py           CoT deception, tool injection, escalation
│
├── longitudinal/                 Time-Series / Sequential
│   ├── temporal_robustness.py      Noise, segment shift, time-warp, burst dropout
│   ├── concept_drift.py            Covariate/label/prediction drift, PSI, staleness
│   └── sequence_safety.py          Look-ahead bias, leakage, anomaly injection
│
└── common/                       Cross-cutting (all model types)
    ├── privacy.py                  MIA, model extraction, attribute inference, DP audit
    ├── alignment.py                Reward hacking, shortcut detection
    └── governance.py               Model card, NIST / EU AI Act compliance
```

---

## Quick Start

### CLI

```bash
# List all checkers (with model-type layer and dependency status)
aisafety list

# Filter by model type
aisafety list --type llm
aisafety list --type cnn
aisafety list --type tree
aisafety list --type longitudinal

# Generate a starter config
aisafety init

# Run a single checker
aisafety run fairness --config aisafety.yaml

# Run a full audit (auto-filters by target.type)
aisafety audit aisafety.yaml
```

### Python API

```python
from aisafety.checkers.tree.fairness import FairnessChecker

checker = FairnessChecker()
result = checker.check(
    y_true=y_test,
    y_pred=model.predict(X_test),
    sensitive_features=gender,
)

for finding in result.findings:
    print(f"[{finding.status.value}] {finding.title}: {finding.description}")
```

```python
from aisafety.checkers.llm.prompt_safety import LLMPromptSafetyChecker

checker = LLMPromptSafetyChecker()
result = checker.check(
    llm_endpoint=lambda prompt: my_llm(prompt),
    system_prompt="You are a helpful assistant.",
)
```

```python
from aisafety.core.report import ReportBuilder

builder = ReportBuilder(target_description="My Model v2")
builder.add_result(fairness_result)
builder.add_result(privacy_result)
report = builder.build()
builder.to_json("safety_report.json")
```

---

## Checker Reference

### CNN / Vision Layer

| Checker | Category | Checks |
|---------|----------|--------|
| **Adversarial Robustness** | `adversarial` | FGSM, PGD, BIM, C&W (L2/L∞), DeepFool, JSMA, ElasticNet, AutoAttack, APGD, Square, ZOO, HopSkipJump, Boundary, Spatial, Pixel, Patch, Universal, Feature Adversaries, Backdoor. OOD detection (MSP + energy score). Gradient masking detection. Input edge-case validation. |
| **Corruption Robustness** | `cnn_robustness` | Gaussian noise, Gaussian blur, contrast/brightness, salt-and-pepper noise, patch occlusion. Mean Corruption Error (mCE) metric across 5 severity levels. |

### Tree / Tabular Layer

| Checker | Category | Checks |
|---------|----------|--------|
| **Fairness & Bias** | `fairness` | Demographic parity, equalized odds, disparate impact (4/5ths rule), subgroup performance gap. |
| **Data Safety** | `data_safety` | PII scanning (presidio), class imbalance, chi-squared bias detection, z-score poisoning detection. |
| **Interpretability** | `interpretability` | SHAP (Tree/Kernel), LIME, cross-method consistency, feature dominance check. |

### LLM / Transformer Layer

| Checker | Category | Checks |
|---------|----------|--------|
| **Prompt Safety** | `llm_prompt_safety` | 60+ prompt injection tests (direct, indirect, encoding, unicode, structural, multi-turn, cross-language). 50+ jailbreak templates (DAN, many-shot, crescendo, cipher, gaslighting, virtualization). System prompt leakage detection. |
| **Content Safety** | `llm_content_safety` | Toxicity (detoxify), harmful content refusal (40+ categories incl. CBRN), false refusal rate, sycophancy, hallucination/confabulation, stereotype reinforcement, copyright reproduction, response consistency. |
| **Guardrails** | `llm_guardrails` | OWASP LLM Top 10 coverage: PII redaction, XSS/injection output filtering, rate limiting, token limits, resource exhaustion, input sanitization (null bytes, CRLF, ANSI), error information leakage. |
| **Agentic Safety** | `agentic_safety` | Tool risk classification, permission audit (least-privilege), tool call validation, escalation detection, excessive agency, tool output injection, chain-of-thought deception analysis, self-modification detection, reasoning loop detection, data exfiltration patterns, function schema abuse. |

### Longitudinal / Time-Series Layer

| Checker | Category | Checks |
|---------|----------|--------|
| **Temporal Robustness** | `temporal_robustness` | Point-wise noise injection, segment shift attack, time-warp attack, random/burst dropout, temporal distribution shift detection. |
| **Concept Drift** | `concept_drift` | Covariate drift (KS statistic), prediction drift (JS divergence), label drift, model staleness (windowed performance decay), Population Stability Index (PSI). |
| **Sequence Safety** | `sequence_safety` | Look-ahead bias detection, temporal ordering validation, train-test data leakage, anomaly injection robustness, autocorrelation memorization, label distribution consistency. |

### Common Layer (All Model Types)

| Checker | Category | Checks |
|---------|----------|--------|
| **Privacy** | `privacy` | Black-box MIA, label-only MIA, model extraction/stealing, attribute inference, confidence score leakage, canary-based memorization, DP training detection, generalization gap analysis. |
| **Alignment** | `alignment` | Reward hacking detection (reward-GT correlation), reward-objective divergence, shortcut/degenerate behavior, action diversity. |
| **Governance** | `governance` | Model card generation, completeness audit, NIST AI RMF compliance mapping, EU AI Act risk classification, safety checklist coverage audit. |

---

## Configuration

```yaml
# aisafety.yaml
target:
  description: "Credit Scoring Model v2"
  type: "tree"  # cnn | tree | llm | longitudinal

checkers:
  # Tree / Tabular
  fairness:
    enabled: true
    threshold: 0.1
  data_safety:
    enabled: true
    text_columns: ["description"]
    sensitive_columns: ["gender", "race"]

  # Common
  governance:
    enabled: true

output:
  format: "json"
  path: "safety_report.json"
```

When `target.type` is set, `aisafety audit` auto-filters to checkers applicable to that model type (layer-specific + common).

---

## Installation

```bash
# Core (CLI + report framework, no ML dependencies)
pip install -e "."

# By layer
pip install -e ".[fairness]"         # fairlearn
pip install -e ".[adversarial]"      # ART + PyTorch
pip install -e ".[interpretability]" # SHAP + LIME
pip install -e ".[llm]"             # detoxify + presidio + openai
pip install -e ".[data]"            # presidio + pandas
pip install -e ".[privacy]"         # ART
pip install -e ".[governance]"      # jinja2

# Everything
pip install -e ".[all]"

# Development
pip install -e ".[dev]"             # pytest + ruff
```

---

## Safety Checklist

### Data Safety
- [ ] Training data audited for biases (gender, race, age, etc.)
- [ ] PII removed or anonymized
- [ ] Data provenance documented (sources, licenses, consent)
- [ ] Poisoning detection — validate data integrity before training
- [ ] Class imbalance assessed and mitigated

### Model Robustness
- [ ] Adversarial attack testing (FGSM, PGD, C&W, AutoAttack)
- [ ] Out-of-distribution detection implemented (MSP, energy score)
- [ ] Corruption robustness tested (noise, blur, occlusion)
- [ ] Input validation and sanitization
- [ ] Gradient masking vulnerabilities checked
- [ ] Distribution shift handled gracefully

### Fairness & Bias
- [ ] Demographic parity, equalized odds measured
- [ ] Performance disaggregated across subgroups
- [ ] Disparate impact assessment (4/5ths rule)
- [ ] Bias mitigation applied (pre/in/post-processing)

### Interpretability
- [ ] Feature attribution methods applied (SHAP, LIME, Grad-CAM)
- [ ] Cross-method consistency verified
- [ ] Model decisions explainable to stakeholders

### Privacy & Security
- [ ] Membership inference attack resistance tested
- [ ] Model extraction/stealing defenses in place
- [ ] Attribute inference attack tested
- [ ] Differential privacy applied where needed
- [ ] Confidence score leakage assessed

### Alignment
- [ ] Reward function reviewed for misspecification
- [ ] Reward hacking / shortcut learning tested
- [ ] Goal misgeneralization evaluated

### LLM: Prompt & Output Safety
- [ ] Prompt injection resistance tested (60+ patterns)
- [ ] Jailbreak resistance evaluated (50+ templates)
- [ ] System prompt leakage prevented
- [ ] Hallucination rate measured
- [ ] Sycophancy and over-agreement evaluated

### LLM: Content & Behavior
- [ ] Harmful content refusal tested (40+ categories incl. CBRN)
- [ ] False refusal rate (over-refusal) measured
- [ ] Stereotype reinforcement checked
- [ ] Copyright/verbatim reproduction tested
- [ ] Response consistency across rephrasings

### LLM: Deployment Guardrails
- [ ] OWASP LLM Top 10 coverage verified
- [ ] PII redaction in inputs and outputs
- [ ] XSS/injection output filtering
- [ ] Rate limiting and token limits enforced
- [ ] Error responses don't leak sensitive information
- [ ] Input sanitization (null bytes, CRLF, unicode)

### LLM: Agentic Safety
- [ ] Tool calls validated and sandboxed
- [ ] Least privilege for tool permissions
- [ ] Chain-of-thought monitored for deception
- [ ] Tool output injection resistance tested
- [ ] Self-modification blocked
- [ ] Reasoning loop detection in place

### Time-Series: Temporal Safety
- [ ] Temporal perturbation robustness tested
- [ ] Concept drift detection implemented
- [ ] Look-ahead bias / temporal leakage checked
- [ ] Model staleness monitoring in place
- [ ] Missing data and burst dropout handled

### Governance & Compliance
- [ ] Model card published
- [ ] NIST AI RMF risk categories covered
- [ ] EU AI Act risk tier classified
- [ ] Red-teaming conducted
- [ ] Incident response plan documented

---

## Reference Frameworks

- [NIST AI Risk Management Framework](https://www.nist.gov/artificial-intelligence/risk-management-framework)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [EU AI Act](https://artificialintelligenceact.eu/)
- [ISO/IEC 42001](https://www.iso.org/standard/81230.html)

---

## License

MIT
