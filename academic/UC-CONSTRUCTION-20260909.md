# Scoped UC4SS construction — September 9, 2026

The canonical manuscript now includes an ideal functionality, an explicit
simulator and a written real/ideal execution proof for a restricted
authorization-record service. This completes a scoped specification-level
argument. It does not establish a concrete cryptographic implementation,
machine-checked theorem or UC security of the full deployed MRA workflow.

The earlier [feasibility assessment](UC-FEASIBILITY-20260909.md) is retained
as a historical snapshot.

## What is now specified

| Component | Construction | Claim boundary |
|---|---|---|
| Application kernel | A public deterministic reducer implementing attributed records, ordered stages, current roles and logical time, exact references, permanent effect tokens, resource charges and portfolio-version checks. | Bounded scientific checkers are explicit parameters. Their measurement premises are not made true by the reducer. |
| Ideal functionality | Separate attributed input and output queues; processing happens only on input delivery, and returning a receipt is a separate event. | All transmitted evidence and metadata are public leakage. Outputs are records, not model execution or redeemable credentials. |
| Real hybrid protocol | Client adapters, public authenticated request/response channels and one honest persistent coordinator running the reducer locally. | No ideal registry makes application decisions. Atomic local execution and authenticated transport are assumptions. |
| Simulator | Runs the real adversary, translates direction/service-specific handles, mirrors notifications and forwards permitted deliveries and corrupted-party submissions. | It is independent of the environment and auxiliary input, and never receives an oracle for scientific truth. |
| U1 | Induction over every declared interface preserves equal application state, request queues, response queues, honest-client pending state and observable outputs. | Perfect equality is in the specified UC4SS authenticated-channel hybrid with static parties and corruption. |
| U2 | Compatible transport substitution adds the error of a separately established channel-network realization. | No repository signing helper has been proved to realize that exact network. S1 alone is insufficient. |

The [main section](paper/uc-section.tex) and
[full appendix](paper/uc-appendix.tex) contain the statements and proofs.
The [rebuilt 43-page manuscript](../output/pdf/manuscript-20260909-uc-construction/mra-paper.pdf)
places the new section on pages 11–12, the kernel and construction in
Appendix E on pages 27–33, the kernel table on page 29, the functionality
and simulator on page 31, and the proof on page 32.

## Corrections made during adversarial review

Separate agent reviews identified concrete interface and state mismatches:

- Pending client state is now installed before a yielding Send; result
  delivery removes it before yielding to the environment.
- Transport validation is identical on honest, corrupt, real and ideal
  paths, before counter allocation or leakage. Bounded malformed
  application data still reaches the reducer.
- Simulator delivery flags are consumed before callbacks. Unknown or
  malformed calls yield without awaiting nonexistent responses.
- The state explicitly stores current policy as well as directory data.
- Portfolio history uses unique instance/candidate/record references;
  precommit and postcommit portfolio versions are distinct.
- Global Admin/Tick requests have their own schemas. Resource charges
  are nonnegative and checked before subtraction.
- Nonvacuity is existential over an accepting checker initialization;
  realization itself also holds for a reject-all checker.

No remaining counterexample was identified in those focused reviews after
the corrections. These are AI agent reviews, not external human peer review,
mechanized verification or a production-security assessment.

## Bounded scheduling evidence

The new [scheduling checker](scripts/check_uc_scheduling.py) uses two separately
expressed machines for an initially ACTIVE Grant/Revoke/Tick skeleton.
Six fixed scenarios cover every interleaving of three
Submit/Receive/Deliver chains, including prefixes:

- 10,080 complete schedules.
- 31,488 scenario-indexed prefix comparisons, including six empty prefixes.
- 31,482 transitions, at most nine actions per complete schedule.

All normalized states and public traces match. Three intentionally incorrect
variants yield public counterexamples: processing at submission, re-executing
at receipt delivery, and reapplying a duplicate token's effect.
The last can record two grants with remaining budget minus one.

The [fresh receipt](../output/uc-scheduling-20260909/20260909T141334.611404Z-7f103b9c/results.json)
retains the scenarios, bounds, positive witnesses and negative traces.
Its script SHA-256 is
99a488a8087dfab9f4ad80b93c2165a1ede51e4d8b67f1ddc652a5dc776a74b6.

This is not the full kernel, a UC runtime or a cryptographic test. In
particular, the skeleton caches denied requests and does not implement
the appendix's distinct historical-result wrapper or arbitrary input
conflicts. Its role is to test scheduling and absence of repeated effects.
It does not verify the theorem's quantifiers. Both machines and their
shared harness were written by one AI agent.

## Primary sources and limits

- [Canetti's August 2025 UC tutorial](https://www.bu.edu/riscs/files/2025/08/Canetti.pdf):
  static-system interfaces, ideal wrappers, simulator quantifiers,
  delivery/leakage and compatible composition.
- [Canetti's corrected August 15, 2004 signature/certification/authentication paper](https://eprint.iacr.org/2003/239.pdf):
  signature realization and authenticated communication require their
  stated certification and session conditions.
- [Canetti, Shahaf and Vald, PKC 2016](https://www.iacr.org/archive/pkc2016/96140235/96140235.pdf):
  global PKI introduces transferability concerns beyond ordinary local
  ideal authentication.

These full primary sources were accessible and the relevant definitions
and results checked. They supply the framework and prior constructions,
not validation of this manuscript. No bare-network impossibility result
has been generalized to the application as a whole.

## Verification and remaining work

Nineteen existing manuscript artifact checks pass; static TeX references,
citations and environment checks pass; all 109 historical evidence digests
still match. The PDF was compiled offline with the existing Tectonic
installation and every page was visually reviewed. No overfull boxes,
missing characters, unresolved references or out-of-page words remain.
Ordinary underfull-box and class font-substitution warnings remain in
the logs. The first attempt's unavailable-font failure is retained.
The [build receipt](../output/pdf/manuscript-20260909-uc-construction/build-receipt.json)
records final source, compiler and PDF hashes.

No model training, dependency installation, new Lean execution, production
code edit or historical-evidence overwrite occurred. Prior PDFs and reports
remain intact. Pre-edit source copies are under
output/uc-construction-20260909/before/.

The result proves faithful execution of the modeled procedure over public
attributed inputs. It supplies no empirical assurance of truthful evidence,
lawful authority, confidential storage, global-state correctness or actual
model serving. Fixed statistical alpha remains a separate scientific
soundness budget because both ideal and real systems run the same fallible
checker. The centralized simulation method is standard; its integration
and precise boundary are the contribution here.

The three next research steps are to mechanize this exact machine/interface
model, establish a compatible concrete transport realization, and prove
implementation correspondence for an integrated authorization and serving
system before claiming deployed UC security.
