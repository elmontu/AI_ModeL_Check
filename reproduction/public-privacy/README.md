# Public-data privacy audit

The workflow is orchestrated through RAG and MCP. `plan_privacy_audit` retrieves applicable
family-specific requirements and limitations from the hashed MRA knowledge index, emits a versioned
plan, and binds it with SHA-256. `run_rag_guided_privacy_audit` freezes that plan and launches the
controlled worker. The worker report embeds the plan ID, plan hash, and retrieved citations; the MCP
service rejects a mismatched report.

`scripts/run_public_privacy_audit.py` downloads public MNIST and Adult snapshots through OpenML and
the public 20 Newsgroups corpus through scikit-learn. It trains independent target/reference CNN,
LSTM, XGBoost, and compact Transformer text classifiers. A per-example loss threshold is selected
only on the reference model's disjoint member/nonmember calibration populations, then evaluated on
the target model's member/nonmember audit populations.

The retained report records source identifiers, processed snapshot hashes, seeds, software versions,
utility, raw losses, attack counts, equal-prior membership success, and a one-sided 95% exact binomial
lower bound. These are attack floors/screens. They may demonstrate leakage and block a release; weak
or null attacks never clear one.

The compact Transformer is an LLM architecture proxy for an affordable public-data experiment, not
a production-scale LLM or a complete interactive transcript audit. Public preprocessing is outside
any claimed private mechanism.

Run in an environment containing the `experiments` dependencies plus PyTorch:

```bash
python scripts/run_public_privacy_audit.py
```
