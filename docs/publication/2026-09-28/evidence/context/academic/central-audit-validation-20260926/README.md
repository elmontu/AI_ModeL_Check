# Central accounting and person-level model exports

26 September 2026. This revision implements and evaluates the highest-impact
items from the central-agency reassessment. It does not claim an agency deployment.

The question is whether one authority can account correctly for models that
different recipients may combine, and which private computations still support
useful models. A graph records dependencies; privacy comes from valid mechanisms
and complete accounting over the people affected by those dependencies.

## What changed

- The bounded local gate now registers fixed people, aliases, dataset versions,
  contribution bounds and approved mechanism certificates. It reserves a common
  allowance before a computation can be committed. Recipient labels never reset
  the account. Reuse refers to one actual execution, not equal model bytes.
- Pure-DP and Gaussian/zCDP accounts are separate. Row-level bounds are converted
  using each person's contribution, while already person-calibrated certificates
  are charged once. Unknown aliases and unsupported correlated mechanisms block.
- Model packages are bound to committed sources. Cap refusals survive restart;
  revocation blocks later delivery without refunding old disclosures. Abandoned
  reservations remain charged. An independent review found and corrected missing
  dependency-index checking in the full audit.
- A matched benchmark compares the graph with a strong cached exact ledger and
  a sound coarse account. A follow-up batches alias registration after setup
  transactions were measured as a bottleneck. Original timings are preserved.
- New utility experiments aggregate and clip each person's complete contribution.
  Model tasks, observation counts, signal and correlation replace named dataset
  attributes as factors. Existing record-level studies keep their original scope.

Implementation and commands: [gate documentation](../../docs/central-audit.md).
Written conditions and counterexamples: [theory.md](theory.md).
Current research direction: [research plan](../research-plan-20260926.md).
Revised manuscript: [PDF](../../output/pdf/manuscript-central-validation-20260926/mra-paper.pdf)
and [canonical TeX](../paper/mra-paper.tex). The main text occupies ten pages,
references pages 11–12, and retained appendices pages 13–32. This is a combined
working draft, not a submitted paper or a final submission package.

## What the evidence establishes

| Claim | Evidence | Boundary |
|---|---|---|
| Serialized reservations preserve the declared common account | Written invariant; 30 gate tests including 216 enumerated small histories; independent mutation probes | Conditional on valid mechanisms, true identity mapping, durable authority and complete mediation; not machine-checked or malicious-host security |
| Exact ledger and graph give the same decisions | 108 matched trials, 2,808 oracle-checked proposals, 36 paired histories, zero mismatches | Synthetic public membership; does not measure privacy of arbitrary training |
| Verified overlap can admit more releases | Disjoint case: both exact methods admit 24/24, coarse 10/24; complete overlap: all 10/24 | Membership information gives the gain, not graph notation or a new composition rule |
| Graph indexing improves runtime generally | Not supported: reference admission 5.918 versus 5.933 ms; 1,024-person case 11.499 versus 11.221 ms, ledger versus graph | Three repetitions, retained scheduling/filesystem outliers; graph can use more space |
| The gate can mediate actual fitted model packages | Five Gaussian coefficient models, 600 people/1,800 rows, two recipients/model; common rho=1/5; sixth computation refused before noise; independent package replay | Trusted producer; OS-backed floating Gaussian is not a finite-machine DP certificate |
| Person aggregation avoids automatically charging once per row | Sensitivity at most twice the person clipping radius; controlled utility comparison across row counts | Replacement of fixed members' values; objective uses person averages; not participation privacy |
| Generic reuse is better than all central alternatives | Not supported: known-workload joint mechanism matches full-span reuse and can improve on a low-rank workload | The stronger control knows the task set in advance; all response coordinates already exist |
| Repeated fresh computation can waste an allowance | 64 independent worlds, two noise draws/world; at 20 exports the displayed fresh-minus-joint MSE differences are 0.1029–0.1342 | One synthetic moment learner; post-hoc public-range clipping; no all-model or SLM conclusion |
| The tasks require access to protected training data | Not established: the known-generating-law public control is better in the displayed examples | Public-law knowledge is a deliberately strong diagnostic, not a typical agency assumption |

## Preserved evidence and version boundaries

- [Frozen scope](PLAN.md), [before sources](before/).
- [Matched benchmark report](gate/benchmark-v2/REPORT.md) and
  [raw summary](gate/benchmark-v2/summary.json). Twelve settings, three matched
  incidence realizations, three representations. Reference/oracle checks are
  excluded from measured operational phases. Database bytes exclude process
  memory and filesystem caches. Benchmark source snapshots bind the original
  implementation; later alias batching does not rewrite these measurements.
- [Gate tests](gate/test-run-v2.json) and
  [independent final checks](independent-gate-review-bulk-final.json).
- [Atomic batch follow-up](gate/benchmark-v3/REPORT.md): 18 trials, nine paired
  histories, 128/512/1,024 people and two aliases/person. At 1,024 people the alias
  phase falls from 13.0933 +/- 0.6914 s to 0.01981 +/- 0.00165 s (sample SD,
  three repeats). All downstream states and delivered bytes agree. The complete
  tiny fixture path falls from 13.2403 to 0.16470 s; this is not model-training
  throughput. [Gate evidence index](gate/README.md) binds all code versions.
- [Actual model integration](integration-v3/result.json),
  [recipient replay](integration-v3/recipient-replay.json).
  The recipient reconstructs predictions from delivered coefficients and public
  test features without opening the authority database or training records.
  Earlier integrations remain separate. In particular, v1's public deterministic
  noise was a fixture, not evidence of private randomness.
- [Original utility run](utility/run-v1/environment.json): 64 independent worlds,
  46,080 alternative arm histories, 399,360 coefficient records. Profiles reuse
  nested population prefixes; noise repetitions are not new population draws.
  Each arm's allowance concerns that hypothetical history separately, not joint
  publication of every experimental alternative.
- [Follow-up analysis](utility/analysis-v3/summary.csv),
  [paired contrasts](utility/analysis-v3/paired-contrasts.csv),
  [verification](utility/analysis-v3/verification.json). Original unbounded losses
  are retained. The follow-up was frozen after observing failures and before
  execution; it is explicitly post hoc. It clips predictions to a public range
  without changing coefficients. Analysis-v3 renames ambiguous diagnostic fields
  from v2 without changing endpoints or intervals. Noise draws are averaged within
  each world before pointwise, unadjusted paired intervals are calculated.
- The unfinished benchmark-v1 is preserved with its stop explanation. No failed
  trial was replaced by a more favorable value. Historical large-corpus, SLM and
  deletion experiments remain historical evidence under their original contracts.

## Practical decisions from these results

1. Use the exact ledger as the initial operational default; expose its dependency
   graph for explanation and audit. Do not assume graph indexing pays for itself.
2. Use atomic batch registration for bulk metadata. Measure this separately from
   training, privacy mechanism quality and the original representation benchmark.
3. Prefer a person-calibrated approved mechanism when person protection is needed.
   Reusing a row-level parameter without recalibration is unsound.
4. When future tasks and required labels are known, compare one workload-aware
   private computation with repeated training. Unknown future labels need new
   evidence/computation; naming them post-processing does not resolve the gap.
5. Keep previous model exposures charged after revocation or deletion. Removal
   needs its own trainer-relative guarantee; dependency traversal is insufficient.

The remaining deployment boundary includes truthful cross-system identity mapping,
authenticated producers, complete export mediation, private selection/evaluation,
certified numerical sampling and an external defense against coherent account
forks. A graph cannot establish these by recording assertions. A production trial
needs that concrete boundary; no government or ethics review package is implied.

## Reproduction and manuscript checks

The data/algorithm evidence is preserved under the frozen plans above. Running
`verify_revision.py` checks manuscript links, distinct labels, citation keys, code
bindings for tests/integration, frozen benchmark versions and all 28 utility
manifest entries. It is document/evidence consistency checking, not theorem proving.
The 30 gate tests and 76 additional regression/document tests passed; the
[additional test record](additional-test-results.json) retains the corrected
cross-reference failure from the manuscript restructuring.

Compilation uses the existing repository assets; no dependencies were installed:

```powershell
$env:TECTONIC_CACHE_DIR = (Resolve-Path '.local/tectonic-cache-20260924').Path
.local/tectonic-0.17.0/tectonic.exe -X compile --only-cached --keep-logs --keep-intermediates -Z 'search-path=tmp/pdfs/full-revision-tex-assets' --outdir output/pdf/manuscript-central-validation-20260926 academic/paper/mra-paper.tex
```

The final log has no overfull boxes, unresolved references/citations or duplicate
destinations. All 32 pages were rendered and inspected; the new result table and
accounting/person-level equations also received larger-scale inspection. Source
and PDF hashes bind the [final artifact receipt](final-artifacts.json).
