# Security-proof revision — September 9, 2026

The previous manuscript had conditional protocol/statistical proofs and an
inventory of symbolic Lean results, but no explicit computational
authentication experiment and reduction. That was a substantive gap.

The [canonical manuscript](paper/mra-paper.tex) now includes a dedicated
[security section](paper/security-section.tex) and
[full security proofs](paper/security-proofs.tex).
In the [rebuilt 35-page PDF](../output/pdf/manuscript-20260909-security/mra-paper.pdf),
the security section begins on page 8, statements are on pages 9–10, and
Appendix D contains the proofs on pages 24–25.

| Statement | What the written proof establishes | Essential limits |
|---|---|---|
| S1: envelope/object correspondence | An accepted envelope attributed to a protected issuer matches previously issued typed content and captured reference bytes, except with probability bounded by N times the single-key signature-forgery advantage plus the hash-collision advantage. | Pinned, uncompromised keys; injective typed encoding; captured original preimages; polynomial resources. Correspondence is not evidence truth or a unique signing event. |
| S2: at-most-once effect and current admission | A persistent signed token causes at most one new atomic effect; fresh-head comparison prevents two commits against one predecessor; current status, epoch and strict deadlines exclude old authorizations at grant time. | Explicit atomic token/effect persistence, no rollback/head reuse and faithful current-state reads. This strengthens sequential A1 handling; A5's commit nonce alone is insufficient for every stage. No physical output-delivery deadline is proved. |
| S3: composition with ordinary privacy release | Under the scientific and lifecycle premises in the same adaptive experiment, registered-threshold violations at ordinary grants are bounded by alpha plus the S1 cryptographic terms. | Every supporting issuer belongs to the protected set. Statistical validity covers adversarial scheduling and selection. Authentic fabricated measurements, hidden channels, RWR and unmediated serving are not silently charged to alpha. |

The proofs use the first correspondence failure consistently in both
reductions. The collision case retains both actual byte preimages.
The composition proof uses event inclusion rather than conditioning
statistical calibration on cryptographic success. Explicit counterexamples
explain authentic false evidence, registry rollback, delayed delivery,
compromised keys and joint disclosure.

The reduction applies the established chosen-message unforgeability notion
described by [Goldwasser, Micali and Rivest](https://epubs.siam.org/doi/10.1137/0217017).
The publisher's abstract and bibliographic metadata were accessible; its
full text requires access. Ed25519 is identified as established external
work through the [original design paper](https://ed25519.cr.yp.to/ed25519-20110926.pdf)
and the [official RFC 8032 specification](https://www.rfc-editor.org/rfc/rfc8032.html).
These primary sources were checked on September 9, 2026; none is presented
as a proof of this repository's implementation.

Two separate agent reviews identified missing precision about head
advancement, invalidation persistence, reduction stopping and the A1/A5
replay mapping. Those points were corrected. This is not external human
peer review, machine checking or independent institutional validation.

Nineteen existing manuscript artifact tests passed. All 109 historical
source digests still match; source references/citations and the independent
study companion replay consistently. The PDF was compiled offline with
the existing Tectonic installation and all 35 pages were visually checked.
No overfull boxes, missing characters, out-of-page words or unresolved
reference markers remain. Ordinary underfull-box and class font-substitution
warnings are retained in the build log.

No model training, dependency installation, Python implementation changes,
fresh Lean run or historical-evidence overwrite occurred. The earlier PDF
and all prior receipts remain separate. Pre-edit copies are under
output/security-proof-revision-20260909/before/.
The signature/serialization/registry construction still requires
implementation correspondence and external mathematical review before
broader security claims are warranted.
