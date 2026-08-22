# Literature-driven critique and refresh of assurance checks

**Review date:** 2026-08-22

## Executive assessment

The refreshed checks are materially stronger for research and offline screening, but MRA is still not a production authorization gate. The main improvement is semantic: every empirical result now stays on the lower-bound side of the assurance model, and checks that lack the required interface, statistical family, or recipient-realizability information fail closed.

The audit's release-provenance blocker is resolved in version 0.6. Analyzer sources contain the complete framework-owned payload plus a source-observed context binding the release contract, policy, artifact, interface, population, decision game and observation time. The engine validates this envelope before analysis, and analyzers copy it into evidence records without post-analysis restamping. Production use still requires independently operated workers and attestation that the source-observed values are truthful.

## Check-by-check result

| Check | Previous weakness | Refresh | Current judgement |
|---|---|---|---|
| Core membership TPR at low FPR | TPR lower and FPR upper bounds each used the whole declared alpha | Alpha is now divided across both bounds and every declared comparison | Correct conservative joint operating-point check |
| Evidence-class direction | Model allowed semantically contradictory screen/floor/ceiling routing | Screens cannot block or clear; floors cannot clear; ceilings cannot block; auditor-only evidence cannot clear | Fixed at the model boundary |
| Analyzer source payload | Claimant could bind one innocuous field or rebind evidence to a different release/game | Bound fields and the source object exactly equal the complete analyzer payload; a source-observed evidence context binds release, policy, artifact, interface, population, game and time | Resolved in 0.6; worker authenticity remains an operational trust requirement |
| Generic attacks on interactive LLMs | Generic aggregate attack inputs could be stamped recipient-realizable despite lacking transcripts, canary commitments, or contamination checks | Generic attack and controlled-inference analyzers reject `interactive_llm` releases | Correct fail-closed refusal until dedicated analyzers exist |
| Interactive-LLM interface contract | No text access type; query budgets could disagree; adapters, stateful memory, decoding, and expiry were under-checked | Text output, exact lifetime budget, nonempty decoding, adapter digests, stateful TTL, protocol expiry, and release-expiry containment are enforced | Stronger release-side contract; not transcript assurance |
| Incremental controlled-inference policy | Threat/analyzer supported incremental attribute and reconstruction metrics but policy validation rejected them | Policy rules now accept both versioned incremental metrics | Contract inconsistency fixed |
| Assessment signing | Signer could combine a report with an unrelated release and omit or substitute its expiry | Signer verifies the canonical request/release hashes and report-facing release fields; verifier requires exact report/manifest expiry equality | Fixed; signatures now bind the validated request/report pair |
| XGBoost replicate inference | Each seed corrected only its own TPR/FPR pair | Bonferroni family covers both bounds for every registered seed; summary forbids uncorrected best-seed selection | Fixed for the registered single operating point |
| XGBoost deployment interpretation | Equal-prior or attack accuracy could overstate real-world usefulness | Preregistered membership priors produce point PPV and a simultaneous conservative PPV lower bound; point PPV is explicitly undefined when there are no positive predictions | Added; still conditional on the declared priors |
| XGBoost low-FPR support | Impossible tail claims merely produced confusing screens | Manifest reports the minimum zero-FP nonmember count and refuses a floor unless the simultaneous FPR upper bound attains the target | Safe and auditable |
| XGBoost member sample | Half the target members were discarded even though threshold calibration used only nonmembers | All equalized target-training members estimate audit TPR | More power without contaminating threshold selection |
| XGBoost cache | Editing decision-critical manifest conclusions or provenance could survive cache reuse | Raw scores replay the attack and a hash-checked audit-evidence artifact must match utility, structure, game, release binding, attack fields, model parameters, protected unit, and sample/class/group counts | Good corruption/tamper detection; not cryptographic authenticity |
| XGBoost recipient bundle | Public manifest disclosed dataset, config, implementation, and runtime fingerprints | Those internal provenance fields are omitted from the recipient ZIP by default | Release surface reduced |
| XGBoost decision game | Worker admitted that the threat and interface were unbound | Configuration 1.1 requires and hashes a canonical probability-plus-true-label game, records that it is realizable by a full-artifact recipient, and references an external threat contract | Worker-level observation binding added; white-box artifact internals and authoritative MRA policy/population binding remain outside this screen |
| XGBoost attack strength | One reference model could be mistaken for LiRA | Output and documentation say “single-reference loss-difference membership screen” | Correct label; full LiRA/RMIA remains future work |
| LLM preregistration | Combined watermark/canary game, prose-only family, no scheme binding, weak tail plan, no quality/adaptive matrix, contradictory query plan | Profile 1.1 separates games and families, binds scheme and detector, requires null calibration, unique contexts, search registry, power/quality, and twelve adaptive attack classes | Strong preregistration template |
| LLM collection readiness | JSON syntax and a few sentinels were the only executable checks | New linter strictly validates nested contracts, digests, hypotheses, family registries, adaptive attacks, fixed-arm randomization, complete binding coverage, dates, simultaneous tail feasibility, key/tokenizer consistency, concurrency, and all registered query paths; it has a tested successful collection-ready path | Useful protocol linter; emits no scientific evidence |
| Canary modes | Rank exposure, randomized inclusion, and naturalistic extraction were conflated | Randomized IN/OUT is primary; rank exposure is supplementary and auditor-only by default; naturalistic extraction is a separate disabled probe | Correct separation |
| Watermark claim | Detector hit risked being read as provenance/authorship proof | Claim is limited to rejection of a registered no-watermark null for a key-associated detector | Correct narrow interpretation |

## What the checks still do not establish

### XGBoost

- The current attack is not LiRA, RMIA, a white-box GBDT privacy attack, an attribute/property attack, or a reconstruction attack.
- Same-dataset reference sampling does not test temporal, geographic, domain, or acquisition shift.
- Class-level score summaries are descriptive. They are not subgroup privacy bounds and cannot block or clear.
- A full artifact, probability API, label-only API, TreeSHAP endpoint, leaf-index endpoint, and per-tree contribution endpoint are different channels and need separate games.
- Ordinary XGBoost supplies no differential-privacy ceiling. A private GBDT claim requires a specific mechanism, accountant, composition scope, and implementation audit.

### LLM watermarking

- The linter does not generate text, recompute detector scores, validate a null tail, measure power or quality, or execute removal/spoofing attacks.
- A configured detector threshold is not valid until the complete negative corpus and search family demonstrate calibrated simultaneous false-positive control.
- Key-associated detection does not authenticate the provider, model, user, or author.
- Signed logs or content credentials are separate authenticated systems, not assumptions that may be smuggled into a watermark p-value.

### LLM canaries

- No dedicated canary analyzer or one-run privacy-audit statistic is implemented.
- Rank exposure from auditor-only sequence scores is a memorization diagnostic, not evidence available to a text-only recipient.
- Artificial canaries do not estimate leakage prevalence for ordinary records.
- A null attack remains attack-, prompt-, model-, interface-, and budget-specific.

## Remaining blockers and priority

1. **Add dedicated LLM analyzers.** Implement separate watermark, randomized IN/OUT canary, exact-extraction, and transcript/lifetime-channel inputs and replay logic. Keep the optimizer's interactive-LLM refusal until then.
2. **Expand model-family workers.** Use the all-model catalog to prioritize vision, audio, graph, recommender, generative-media and agentic-system evidence rather than forcing them through generic attacks.
3. **Expand XGBoost threat coverage.** Add multi-reference attacks, mismatch sensitivity, full-artifact/TreeSHAP profiles, and preregistered subgroup families before making broader privacy claims.
4. **Add authenticity around worker evidence.** Cache replay detects local inconsistency, but signed independent evidence and managed keys are required against an adversarial submitter.

The [literature review](literature-review.md) supplies the primary-source basis for these judgements. The original [framework audit](audit-2026-08-22.md) remains authoritative for the unresolved provenance and other findings, with refresh-status notes identifying remediated defects.
