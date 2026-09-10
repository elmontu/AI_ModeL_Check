# UC feasibility and game-based revision — September 9, 2026

Assessment: a meaningful UC treatment appears feasible for the technical
release-authorization service under explicit setup and corruption assumptions.
This repository does not yet establish that realization. A functionality
guaranteeing truthful evidence, universally safe disclosure or correct
institutional judgment is a different target; the present cryptographic
mechanisms cannot supply those properties on their own.

This is a research assessment, not a UC theorem, external peer review or
government/ethics review package. The manuscript continues to claim written
game-based reductions and conditional state/statistical results.

## A useful functionality to attempt

A candidate ideal release-authorization functionality would maintain:

- Registered instance, policy, roles, artifact/interface and evidence bindings.
- Attributed submissions, stage-specific approvals and fixed bounded checkers.
- Current lifecycle status, cumulative disclosure history, budget reservations,
  consumed tokens, registry head, authorization epochs and deadlines.
- Atomic authorization, activation, revocation and service-grant operations.

It would reject missing evidence, impermissible transitions, stale context,
duplicate effects and grants without current authorization. It would preserve
the actual distinctions between a privacy recommendation, optional authorized
risk acceptance, institutional authorization and a live service grant.
Institutional attestations and measured counts would be attributed inputs;
receiving them would not establish their substantive truth.

The functionality must specify its visible leakage: actual public envelope
fields, object hashes, sizes, statuses, receipts and any exposed model outputs.
It must also specify permitted adversarial delays, dropped delivery and
corrupted-party inputs. A grant-time guarantee must not silently become
cancellation of already delivered information or of previously granted output.

## Construction and simulator obligations

A defensible first model could fix static corruptions, keep the registry and
gateway honest, and use approved full public keys, faithful time and a narrowly
specified atomic storage service. These are candidate assumptions, not facts
established for the Python deployment.

Atomic storage should supply storage/transaction behavior, not decide the
whole release-authorization predicate. Otherwise the proof risks assuming its
main result as a setup service. Concrete protocol parties must still implement
the lifecycle checks, exact evidence bindings and admission logic.

The simulator would run the real adversary, reproduce the permitted public
transcript, relay permitted actions to the ideal service, and match delays,
receipts and effects. Outside signature-forgery and hash-collision events, a
relational invariant would have to show that every observable honest output
and state transition has the same counterpart in the ideal execution. This is
substantially stronger than showing that a few forbidden events do not occur.

Signature simulation requires a precisely specified key-registration/signature
setup, including internally generated receipts. Simulation cannot invent
unavailable private inputs or assume a programmable hash merely from collision
resistance. Adaptive corruption additionally requires consistent disclosure of
the corrupted party's past state, keys and randomness; the current S1 model
excludes protected-key corruption.

Shared keys, trust directories, clocks and cumulative budgets require an
explicit treatment of shared state. Per-instance identifiers alone do not
establish a composition theorem for other protocols using those same resources.
A shared-resource UC variant or an applicable joint-state argument may be
needed, depending on the chosen interfaces.

## Three concrete obstacles to a stronger target

1. **Authentic false evidence.** An authorized worker can sign fabricated
   low-risk measurements while the deployed channel reveals a secret.
   If the real system accepts and grants access, an environment that knows
   the channel can observe that grant. A perfectly safe ideal functionality
   that refuses it has different honest-party output. Attribution does not
   fix this mismatch. The manuscript already identifies the false-evidence
   counterexample in [the security section](paper/security-section.tex)
   (paragraph beginning at line 247).

2. **Statistical error versus emulation error.** Theorem 2 and S3 allow a
   statistical failure budget alpha. A bound alpha plus negligible
   cryptographic terms does not establish negligible distinguishing
   advantage when alpha is fixed. An upper bound alone is not an impossibility
   proof: one must exhibit an actual nonnegligible, observable mismatch.
   If such false grants occur, a perfect-safety functionality cannot match
   them. Possible research targets are an ideal service implementing the same
   statistical procedure, a justified negligible alpha(lambda), or an explicit
   quantitative emulation claim. None follows merely by renaming S3's bound.

3. **Hash leakage.** Suppose a hidden random bit is an honest input and the
   real transcript exposes its deterministic hash. An environment that chose
   the bit can check the digest. A simulator given neither the bit nor this
   leakage cannot in general reproduce that correlation. Collision resistance
   does not supply confidentiality. The ideal service must expose the actual
   leakage or the real protocol needs an appropriate confidentiality mechanism.

These are objections to particular stronger functionality/protocol pairs.
They are not a proof that UC is impossible for this application domain.

## Primary-source basis and evidence limits

[Canetti's August 2025 tutorial](https://www.bu.edu/riscs/files/2025/08/Canetti.pdf),
especially slides 22–31, gives the adversary/simulator/environment quantifiers,
a quantitative formulation, and examples showing why leakage and adversarial
delivery must be modeled. The tutorial was accessible in full on September 9,
2026. The
[original FOCS 2001 paper's IBM record](https://research.ibm.com/publications/universally-composable-security-a-new-paradigm-for-cryptographic-protocols)
supports the framework's scope; the original ePrint PDF was blocked during
this session, so no claim is made to have read that full version.

The proposed functionality and simulator above are our application-specific
analysis, not constructions taken from those sources. No UC impossibility
result for commitments or other primitives has been generalized to this
protocol. Game-playing can also be a method inside a simulation proof; it is
not inherently incompatible with UC.

## Completed manuscript changes and validation

The [canonical manuscript](paper/mra-paper.tex) now names its security section
Game-Based Protocol Security. The explicit challenger has Issue, TryAccept
and Schedule interfaces, a first-failure winning event and a probability-based
advantage. All protected signing enters the issuance log, including internally
generated protocol output. S3 uses a coupled continuation with an absorbing
failure flag so its bound covers the full execution after an authenticity
failure. Its title and surrounding text identify a joint failure-event bound,
not UC composition.

The [new 36-page PDF](../output/pdf/manuscript-20260909-game-based/mra-paper.pdf)
contains the security section on pages 9–11, the game box on page 10 and
security proofs on pages 25–26. It was built with the existing offline
Tectonic installation. All pages were visually checked; no clipping or overlap
was found. Ordinary underfull-box and class font-substitution warnings remain.
The final bibliography URL continues onto page 20, a minor layout weakness.
Nineteen existing manuscript artifact tests passed. The build receipt records
source hashes and the historical digest checks.

The first build failed because an offline font was unavailable; its log is
retained. Normal-size game-box text compiled with cached fonts. No dependency
installation, model training, new Lean execution, implementation edit or
historical-evidence replacement was performed. Earlier PDFs and receipts are
preserved; pre-edit source copies are in
output/game-security-revision-20260909/before/.

The next theoretical milestone is a complete functionality, concrete hybrid
protocol and simulator with a relational execution proof. It is not yet
appropriate to replace the manuscript's game-based claims with a UC theorem.
