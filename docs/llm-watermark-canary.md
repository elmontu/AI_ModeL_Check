# LLM watermark and canary testing

## Scope and assurance boundary

This protocol covers two different questions for an interactive LLM release:

1. **Output watermark detection:** does generated text contain a predeclared, detector-visible statistical signal associated with a particular generator or deployment?
2. **Training-data canary exposure:** can an allowed recipient recover a synthetic string that was committed before training and included only in the member condition?

They are not substitutes. A watermark is a property of the output-generation channel; it neither shows nor prevents training-data memorization. A canary experiment probes extraction or membership leakage under one declared attack game; it says nothing about output provenance. Neither study establishes general LLM safety, authorship, copyright provenance, or the absence of undiscovered leakage.

The current MRA core accepts a complete `interactive_llm` protocol contract but does not implement transcript-level interactive-channel assurance. The profile and its linter emit no audit evidence. An eventual isolated worker must emit only `floor` or `screen` evidence with `can_clear: false`. A positive recipient-realizable extraction result may block or trigger investigation. A null, weak, underpowered, unavailable, or auditor-only result is inconclusive and must never authorize a release.

Potentially hostile model loading and live API calls belong in an isolated worker outside the trusted core. The core should receive inert, hash-bound JSON and referenced evidence artifacts.

## Evidence basis

The [privacy-assurance literature review](literature-review.md#llm-memorization-extraction-and-canary-testing) synthesizes the primary conference literature behind this protocol. It distinguishes rank/exposure canaries, randomized IN/OUT audit canaries, and naturalistic extraction probes because they answer different questions and require different ground truth. It also reviews the distribution-shift and membership-label problems that make null LLM attacks especially weak evidence.

The [watermarking review](literature-review.md#llm-output-watermarking) supports only a narrow provenance claim: rejection of a registered no-watermark null for a declared key-associated detector at a calibrated threshold. Audit-grade results require repeated-context handling, empirical null calibration, simultaneous control of every searched key, window, and post-selected threshold, power and quality curves, and adaptive removal and spoofing tests. A detector hit alone does not authenticate a provider or author, and a miss cannot clear provenance or privacy.

The version 1.1 example now separates watermark and canary games, binds the embedding scheme as well as the detector, enumerates multiplicity families and adaptive attacks, records unique-context handling, and keeps rank exposure auditor-only unless the released interface exposes complete sequence scoring. Validate the template with:

```bash
python scripts/validate_llm_audit_profile.py reproduction/llm/audit-profile.example.json
```

Before collection, fill every approved value and run the stricter check:

```bash
python scripts/validate_llm_audit_profile.py \
  reproduction/llm/audit-profile.json \
  --collection-ready
```

The stricter mode rejects required nulls, malformed or placeholder digests, future-dated or expired profiles, incomplete test registries, unsupported tail plans, non-integral canary dose allocation, concurrency mismatches, and complete query plans that exceed the bound lifetime budget. It counts registered calibration, positive-control, retry, quality, adaptive-attack, canary, and naturalistic-probe opportunities. A five-minute future clock-skew allowance is permitted. It is a preregistration linter, not a watermark detector, canary attack, transcript analyzer, or MRA clearance path.

## Common preregistration

Freeze the following before any audit response is observed:

- release artifact and complete interface hashes, including the model/version, tokenizer, adapters, system prompt, retrieval corpus and configuration, tools and policy, memory/reset semantics, filters, decoding parameters, update policy, query/session/concurrency limits, and expiry;
- population scope, protected unit, threat, prior, side information available to the recipient, success metric, threshold, and harm rationale;
- development, calibration, and final-audit prompt partitions, with the final partition inaccessible to model or detector tuning;
- all languages, prompt families, decoders, transformations, prefix lengths, canary repetition levels, checkpoints, models, and adaptive rounds in the inferential family;
- primary statistic, normalization/tokenization rules, detector threshold, stopping rule, exclusions, confidence method, family error budget, and minimum detectable effect;
- analyzer source, immutable container image, dependencies, hardware/runtime class, random-seed commitment, and raw-evidence retention policy.

Exploratory choices belong in a separately labelled development phase. If an audit choice changes after final responses are inspected, seal a new protocol version and use new untouched prompts and canaries.

## Output watermark detection

### Decision game and hypotheses

Define the recipient-realizable observation as the text returned through the released interface after its actual filters, truncation, tools, retrieval, and logging behavior. The primary comparison should use paired or stratified prompts assigned to:

- the bound release channel; and
- an independently specified null channel, such as the same model with watermarking disabled, when this is operationally available and faithfully matched, or a preregistered family of non-watermarked generators.

Register two distinct tests. The **null-calibration** decision requires a simultaneous one-sided upper confidence bound on the empirical false-positive probability to be at or below the operational target; merely failing to reject an unsafe-rate null is not evidence of calibration. The **detectability** test asks whether release-channel detection exceeds the matched-control probability by the preregistered effect. Passing detectability does not repair a miscalibrated null. Report false-positive rate on held-out null outputs and true-positive rate on held-out release outputs with simultaneous one-sided confidence bounds. AUROC, score separation, and calibration curves are useful secondary summaries but do not replace the registered operating point.

A tail claim is invalid when the held-out null sample cannot produce a useful conservative upper confidence bound at the claimed FPR. For example, 500 null outputs cannot validate a \(10^{-3}\) or \(10^{-5}\) operating point even with zero observed false positives.

Where a provider claims a keyed watermark, commit to the embedding and verification key identifiers and digests before sampling. The independent assessor should control an independently committed verification copy or escrowed detector key; record who possesses the embedding key and every party able to derive either key. Never place a key or recoverable seed in the repository or evidence report. Record whether detection consumes token IDs, token probabilities, or only rendered text. Freeze text normalization, Unicode handling, tokenizer version, minimum eligible length, and behavior for refusals and truncated outputs.

### Controls and robustness

Use untouched, content-matched prompts and equal decoding budgets. Include negative controls and, if available, a blinded positive-control generator. Prespecify robustness strata that reflect recipient actions, such as paraphrase, translation, copy-editing, whitespace/Unicode normalization, truncation, and mixed human/model text. These are separate endpoints; do not tune transformations until a desired answer appears.

Record every eligible response, refusal, error, retry, and exclusion. A watermark result is invalid if the detector was tuned on the final outputs, if release and control prompts differ materially, or if the model/provider changed during collection. Detection can support provenance triage only within the tested channel. False positives can misattribute human or other-model text, and watermark absence after editing does not establish non-authorship.

A detector hit means only that the registered detector rejected its declared no-watermark null for that text and key at its calibrated decision threshold. It is not cryptographic proof that a provider generated the text. A watermark may be spoofed or removed, and key compromise invalidates the interpretation. Signed generation logs or content credentials are a separate authenticated provenance control and must be assessed under their own identity, capture, replay, integrity, and key-management assumptions.

### Adaptive removal and spoofing

Run blind transformations before any rule-recovery phase, then separately budget informed attacks. The registered matrix should cover random edits, blind and informed paraphrasing, translation, truncation, mixed text, watermark stealing, distillation, scrubbing, spoofing, multi-key averaging, and detector-oracle optimization. Bind the attack implementation, model and detector query budgets, observed-watermarked-token budget, stopping rule, and semantic/factual quality constraint. A removal or spoofing score without a quality constraint is incomplete, and a public score-returning detector must be treated as an optimization oracle.

## Training-data canary exposure

### Canary construction and secret safety

Use only synthetic, authorization-approved canaries generated from a large, explicitly defined random space. A canary must not contain personal data, credentials, production secrets, proprietary text, executable instructions, URLs, or tokens that could trigger tools or external actions. Do not use live customer data as a canary and do not insert audit canaries into a production training corpus without documented data-owner approval and a removal plan.

Keep plaintext canaries in an encrypted assessor store. The preregistration and public evidence should contain an opaque canary ID plus a keyed commitment (for example, an HMAC held by the assessor). A plain hash is inadequate when the canary space is enumerable. Disable plaintext prompt/response logging where possible; otherwise use an approved encrypted evidence sink with access control, retention, and deletion rules. Reports should publish aggregate cells and commitments, not canary strings.

Construct member canaries and exchangeable nonmember decoys from the same generator. Randomize membership before training, blind the attacking analyst where practicable, and retain the assignment in a sealed roster. Profile 1.1 uses complete randomization with fixed arm sizes; it therefore does not claim independent Bernoulli inclusion bits. A Bernoulli design must instead register its inclusion probability and treat member/nonmember counts as realized values. Prespecify insertion counts, locations, formatting, tokenizer-length strata, and whether duplicates arise elsewhere. Audit the training, retrieval, fine-tuning, evaluation, prompt, and detector corpora for contamination. A canary found in RAG, a system prompt, logs, or evaluation prompts is not evidence of training memorization.

If the provider may retain audit prompts or train on them, record that pathway as contamination for every later model version. Retire exposed or submitted canaries after the study and never reuse them as independent audit material.

### Decision game and metrics

The primary extraction endpoint is an exact match after a frozen, minimal normalization rule. Count a success only when the complete committed canary occurs in an eligible released response. Report successes and trials separately for member canaries and nonmember decoys, query opportunities per canary, unique and repeated hits, and a simultaneous one-sided lower confidence bound on the preregistered leakage contrast or attack success. The randomized canary assignment is the primary inferential unit; repeated prompts and completions for one canary are clustered observations, not independent trials. Substring, edit-distance, semantic, and partial-token matches are secondary screens unless their loss function was fixed in advance.

If the interface exposes complete sequence log probabilities under the bound tokenizer, also report rank-based exposure:

```text
exposure = log2(|R|) - log2(rank of the canary in randomness space R)
```

Freeze `R`, the scoring rule, tokenization, treatment of ties, and any rank-estimation procedure before querying. Call a rank exact only when every candidate is scored or an exact ranking algorithm with proven completeness is used. An estimated rank must include its uncertainty. Sampled completions, top-k tokens, rounded scores, or truncated log probabilities generally cannot identify full rank; in that case mark exposure unavailable rather than manufacturing a number. Perplexity alone is not exposure.

Prompt-only APIs can still support a bounded exact-extraction attack, but its result is conditional on the registered prompt/query budget. Adaptive queries, retries, prefix searches, temperature sweeps, and concurrent sessions all consume attack opportunities and the release's lifetime budget. Treat the complete dialogue—including system-visible messages, tools, RAG results, memory, and resets—as the observation. A one-shot completion must not stand in for an adaptive transcript.

### Hypotheses and controls

For controlled member/nonmember inference, register the null that the attack's success distribution is no better for member canaries than exchangeable nonmember decoys under the same side information and query policy. The alternative is a preregistered positive difference. For direct extraction, register a baseline success probability derived from the random space and the actual number of recipient-realizable attempts. Prefix-only or model-selected candidates cannot silently replace the registered secret or metric.

Useful controls include nonmember decoys, zero-insertion and repetition-dose cells, unrelated prefixes of equal length/frequency, a non-trained checkpoint where available, and retrieval-disabled versus retrieval-enabled cells when the production interface permits that intervention. Controls must use the same prompt templates, budgets, filtering, and scoring. They diagnose pathways; they do not turn an attack floor into a confidentiality ceiling.

Artificial canaries measure the behavior of the registered synthetic construction. Even a confirmed result does not estimate leakage for arbitrary real records, and a null result does not generalize to other records, prompts, or attacks.

## Multiplicity, adaptivity, and uncertainty

Define separate preregistered confirmatory families for watermark and canary questions. Within each family include every confirmatory key, threshold, language, prompt stratum, transformation, model/checkpoint, insertion count, prefix, decoder, and attack variant actually searched. Use an umbrella family only when one joint decision consumes both studies. Allocate each familywise error budget before collection and use a reproducible procedure such as Holm, Bonferroni, or a registered maximum statistic. Profile 1.1 labels the quality and adaptive-attack endpoints exploratory and non-decision-bearing unless a future protocol explicitly registers them in a confirmatory family. Retain the full ledger, including tests that failed, errored, or were excluded.

Use audit data disjoint from threshold selection and attack development. Treat the randomized prompt or canary as the inferential unit and account for paired assignment and within-unit repeated-generation dependence. Report raw counts and both pointwise and simultaneous intervals; release decisions must use the simultaneous bound. A best-of-many score, unadjusted bootstrap interval, or post-selection interval is a screen only. Power calculations and minimum detectable effects belong in the preregistration. Low power means inconclusive, not safe.

## Evidence and provenance contract

The worker output should include, and cryptographically bind, at least:

- schema/protocol/study/analyzer identifiers and versions; UTC start/end times; assessor identity and signature;
- release artifact hash and a canonical complete-interface hash; hashes for the LLM protocol, policy, threat/decision game, population snapshot, and portfolio-registry head;
- every component hash from `LlmProtocolContract`, its validity interval, and a statement that the deployed endpoint was attested to those values throughout collection;
- preregistration/config hash, prompt-partition hash, member/nonmember assignment-roster hash, transformation and normalization specifications, query-policy hash, and multiplicity-ledger hash; the preregistration enumerates these future digest fields, while their actual values are produced and verified after collection;
- embedding-scheme, detector, tokenizer, null-corpus, unique-context, window/alignment-search, quality-study, and adaptive-attack-matrix hashes;
- analyzer source-commit and container-image digests, detector/version and opaque key ID, dependencies, runtime and hardware class, seeds or commitment/reveal records;
- an immutable transcript-manifest hash covering exact prompt/response bytes or token IDs, exposed log probabilities, status/refusal codes, timestamps, session ordering, retries, query schedule, tool/RAG events, and client/analyzer versions;
- raw transcript, detector-score/logprob, cell-count, exclusion/error, and contamination-scan artifact hashes, plus encryption/access/retention metadata for sensitive artifacts;
- intended recipient, side information, actual query/session/concurrency counts, resets, tools/RAG/memory events, failures, retries, and any deviation from protocol;
- metric, direction (`floor` or `screen`), simultaneous confidence level and method, lower bound where valid, coverage limitations, `can_block`, and `can_clear: false`.

Verify source files and all mandatory bound fields before analysis. Version 0.6 requires source-observed release, policy, artifact, interface, population and game bindings and copies them into evidence without post-analysis restamping. A future LLM collection worker must populate that envelope and additionally bind its partitions, scheme, detector, query transcript and protocol artifacts. Until dedicated analyzers exist, this profile must not be treated as a production authorization artifact.

## Decision semantics

| Result | Evidence meaning | Permitted action |
|---|---|---|
| Confirmed watermark signal | Screen or lower bound on detectability in the tested channel | Provenance triage, investigate false attribution and robustness |
| No watermark detection | Inconclusive outside registered power and transformations | Never infer absence or authorship safety |
| Confirmed exact canary extraction through the bound recipient interface | Attack floor under the registered prompts, decoding, side information, and query budget | May block, remediate, or require reassessment |
| Statistically valid randomized IN/OUT canary contrast | Empirical lower bound under the registered inclusion randomization and observation model | May block only through a dedicated, provenance-complete analyzer |
| Rank exposure from auditor-only sequence scores | Memorization diagnostic, not recipient-realizable extraction | Investigate; never relabel as recipient evidence |
| No canary hit / no significant contrast | Inconclusive attack failure | Never clear confidentiality or privacy |
| Missing log probabilities | Rank exposure unavailable | Report exact-extraction results only; do not impute rank |
| Binding, contamination, or protocol failure | Invalid evidence | Fail closed and rerun with untouched audit material |

Watermark detection should normally be routed to provenance/traceability governance, not privacy clearance. Canary leakage should be routed to the registered membership, attribute, or reconstruction threat according to the exact decision game. Both remain conditional on the released interactive protocol and complete lifetime transcript.

## Example workflow

1. Copy [`audit-profile.example.json`](../reproduction/llm/audit-profile.example.json), replace every placeholder, enumerate the actual tests and attacks, run the template linter, and obtain independent approval before model training or audit queries.
2. Generate synthetic canaries in an isolated assessor environment; store plaintext encrypted and publish only keyed commitments. Seal member/nonmember assignment and prompt partitions.
3. Attest the live endpoint to the release and `LlmProtocolContract` bindings. Abort on any mismatch, expiry, or provider/model update.
4. Use development prompts only to debug the worker. Freeze detector, attack, thresholds, normalization, query policy, stopping rule, and multiplicity ledger, then run the linter with `--collection-ready` before the first final-audit query.
5. Collect watermark release/control outputs and canary member/nonmember transcripts on untouched audit prompts. Retain errors, refusals, retries, tool/RAG/memory events, and budget consumption.
6. Compute the preregistered exact statistics and simultaneous one-sided bounds. Mark rank exposure unavailable unless full bound-tokenizer sequence scoring is actually available.
7. Seal raw evidence, emit inert aggregate evidence with complete hashes and provenance, independently replay it, and route only `floor`/`screen` evidence with `can_clear: false`.
8. Destroy or retain plaintext canaries and transcripts according to the approved schedule; record deletion attestations and incident actions for any confirmed exposure.

The example is a lintable preregistration template, not an executable watermark/canary analyzer and not a release authorization.
