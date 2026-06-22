# AI Model Safety Checklist

A comprehensive safety checklist covering deep learning models through large language models (LLMs).

---

## 1. Data Safety

- [ ] Training data audited for biases (gender, race, age, etc.)
- [ ] PII (personally identifiable information) removed or anonymized
- [ ] Data provenance documented (sources, licenses, consent)
- [ ] Poisoning detection — validate data integrity before training
- [ ] Class imbalance assessed and mitigated

## 2. Model Robustness (Deep Learning)

- [ ] Adversarial attack testing (FGSM, PGD, C&W)
- [ ] Out-of-distribution (OOD) detection implemented
- [ ] Input validation and sanitization
- [ ] Gradient masking vulnerabilities checked
- [ ] Model performs gracefully under distribution shift
- [ ] Stress-tested on edge cases and rare inputs

## 3. Fairness & Bias

- [ ] Demographic parity, equalized odds measured
- [ ] Performance disaggregated across subgroups
- [ ] Bias mitigation applied (pre/in/post-processing)
- [ ] Fairness metrics monitored in production
- [ ] Disparate impact assessment completed

## 4. Interpretability & Explainability

- [ ] Feature attribution methods applied (SHAP, LIME, Grad-CAM)
- [ ] Model decisions explainable to non-technical stakeholders
- [ ] Confidence/uncertainty estimates provided with predictions
- [ ] Decision boundaries documented for critical use cases

## 5. Privacy & Security

- [ ] Differential privacy applied where needed
- [ ] Membership inference attack resistance tested
- [ ] Model inversion attack resistance tested
- [ ] Model extraction/stealing defenses in place
- [ ] Federated learning considered for sensitive data
- [ ] Access controls on model weights and APIs

## 6. Alignment (Deep Models)

- [ ] Reward function thoroughly reviewed for misspecification
- [ ] Reward hacking / shortcut learning tested
- [ ] Goal misgeneralization evaluated on held-out environments
- [ ] Human-in-the-loop checkpoints for high-stakes decisions
- [ ] Kill switch / shutdown mechanism in place

---

## 7. LLM-Specific: Prompt & Output Safety

- [ ] Prompt injection resistance tested (direct & indirect)
- [ ] Jailbreak resistance evaluated (DAN, role-play, encoding tricks)
- [ ] System prompt leakage prevented
- [ ] Output filtering for harmful/toxic content
- [ ] Hallucination rate measured and mitigated
- [ ] Grounding mechanisms (RAG, citations) in place

## 8. LLM-Specific: Content & Behavior

- [ ] Refusal behavior tested for dangerous requests (weapons, CSAM, malware)
- [ ] Sycophancy and over-agreement evaluated
- [ ] Consistent persona — no contradictory safety stances
- [ ] Multi-turn manipulation resistance tested
- [ ] Multilingual safety — tested across languages, not just English
- [ ] Code generation reviewed for security vulnerabilities (injection, etc.)

## 9. LLM-Specific: Deployment Guardrails

- [ ] Rate limiting and abuse detection on API endpoints
- [ ] Input/output token limits enforced
- [ ] Content moderation layer (classifier or rule-based) on outputs
- [ ] PII redaction in inputs and outputs
- [ ] Logging and audit trail for all interactions
- [ ] User feedback / flagging mechanism available
- [ ] Automated monitoring for distribution drift in queries

## 10. LLM-Specific: Agentic & Tool-Use Safety

- [ ] Tool calls validated and sandboxed (file access, web, code exec)
- [ ] Principle of least privilege for all tool permissions
- [ ] Chain-of-thought monitored for deceptive reasoning
- [ ] Multi-step plans reviewed for unintended side effects
- [ ] Human approval gates for irreversible actions
- [ ] Recursive self-improvement / self-modification blocked

## 11. Governance & Compliance

- [ ] Model card / system card published
- [ ] Risk assessment completed (EU AI Act risk tier, NIST AI RMF)
- [ ] Red-teaming conducted (internal + external)
- [ ] Incident response plan documented
- [ ] Regular re-evaluation schedule set (quarterly or per-release)
- [ ] Responsible disclosure process for vulnerabilities

---

## Reference Frameworks

- [NIST AI Risk Management Framework](https://www.nist.gov/artificial-intelligence/risk-management-framework)
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [EU AI Act](https://artificialintelligenceact.eu/)
- [ISO/IEC 42001](https://www.iso.org/standard/81230.html)

---

## License

MIT
