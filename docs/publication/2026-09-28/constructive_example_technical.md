# A constructive synthetic planning release

This is a fully specified teaching example, not an experiment on real agency data. The mechanism, population law, threat games, recipient information and policy thresholds are stipulated below. The numerical results follow from exact arithmetic. They do not assert that a real model has achieved this utility or that the current project can issue agency authorisations.

The example is intentionally a small model: a randomized procedure selects one of two constant planning classifiers, `h_0 = low demand` or `h_1 = high demand`. It predicts a population-level demand category, not a person's outcome. A strong collective signal can support a useful prediction even when each person's influence is small.

## Protected data and exact output law

There are 10,001 publicly eligible people. Each contributes either no record or one binary value. Deduplication and contribution bounding are part of the approved computation. Let `S` be the count of contributed ones; neither `S` nor participation indicators are released. A missing record and a contributed zero both add zero to this count.

Define `r = 101/100` and `k = 5000`. The protected computation draws one bit `B` with

`P(B=1 | S=s) = r^(s-k) / (1 + r^(s-k))`.

All probabilities are rational; negative exponents are interpreted as reciprocal powers. The selected model is `h_B`. For a production implementation, exact rational probabilities can in principle be sampled by unbiased random-bit rejection against the numerator and denominator. The supplied verifier checks the mathematical law; it does not certify a production sampler.

The only data-dependent observable is `B`. No dataset-dependent timing, error, selection, acceptance, rejection, metadata or log output is included in the permitted channel. Model identifiers and delivery metadata are fixed independently of protected data. This is a scope assumption requiring implementation evidence in a real release.

Both allowed neighbouring relations are person-level: add or remove one person's entire contribution, or change that person's binary value. Either changes `S` by at most one. Consequently, this mechanism has participation and value protection. That claim is about this hypothetical mechanism, not the project's fixed-membership value-replacement prototype.

## Why either output has likelihood ratio at most 1.01

Write `w = r^(s-k) > 0`. Then `p_s = w/(1+w)` and `p_(s+1) = r*w/(1+r*w)`. With positive common denominator `(1+w)(1+r*w)`, the following differences have nonnegative numerators:

- `p_(s+1) - p_s`: numerator `(r-1)w`.
- `r*p_s - p_(s+1)`: numerator `r(r-1)w^2`.
- `r(1-p_(s+1)) - (1-p_s)`: numerator `r-1`.

Thus both outcomes satisfy the probability-ratio bound in both directions. Counts that do not change have identical laws. This proves pure person-level differential privacy with `epsilon = ln(101/100)` and `delta = 0` on the stated domain. The inequalities hold for every possible count, not just the two regimes used to calculate utility.

## Complete history and recipients

One protected source execution draws `B` exactly once. Recipient A previously received that stored bit; the proposed delivery to recipient B contains the same cached bit. Their pooled transcript is `(B,B)`, with probability zero of `(0,1)` or `(1,0)`. It is exactly equivalent to observing `B` once. Fixed dashboards or repeated queries returning that same stored bit are deterministic post-processing.

The original execution remains charged. A second independent draw from the mechanism would be a new private computation and is expressly excluded. No forgotten earlier model, different record set, side output or independently randomized reply is assumed away. In this finite example there are no other protected computations or disclosures. Approval and activation conditions are determined by this fixed public design, not by privately testing the realized count and selectively disclosing acceptance.

All privacy figures below cover the full pooled history relative to the baseline before the original protected source was disclosed. For the new delivery alone, a coalition that already retained `B` obtains no additional information. This does not remove the original charge or change the original guarantee.

## Membership ceiling

Compare a named person's absent and present worlds while holding the other contributions fixed, or mixing the same background law in both worlds. The present contribution can be zero or one. Any test of the pooled transcript, including a randomized test, has

`TPR <= r * FPR`.

At `FPR <= 1/1000`, the ceiling is `101/100000 = 0.00101`, or **0.101%**, comfortably below the stipulated **1%** detection tolerance. This is a mechanism bound over tests, not a failed membership attack. Eligibility being public does not mean actual participation is public.

## Binary attribute ceiling and its limitation

The protected secret is a named person's binary value. Conditional on allowed auxiliary information, the other contributions must have the same law under either secret value. Equivalently, the argument can condition on a fixed background. It does not bound inference about a person's attribute through a changing, correlated population background.

Let the conditional prior probability of value one be `a`, and the likelihood ratio of an observed output be `l`. Then `1/r <= l <= r`, and the posterior is

`a' = a*l / (1-a+a*l)`.

For `l >= 1`,

`a' - a = a(1-a)(l-1)/(1+a(l-1)) <= (r-1)/4 = 1/400`.

For `l < 1`, relabel the two secret values and use the same argument. Hence the absolute posterior change is at most `1/400`. The best binary classification success `max(a,1-a)` changes by no more than this amount for any output, and therefore also in expectation. The increment in optimal inference success is at most **0.25 percentage points**, below the stipulated **2 percentage point** tolerance. This is an analytical conservative bound; no hypothetical attack score has been substituted for a ceiling.

The proof is robust to a known fixed background. That robustness is not a claim that labelled background records are available in the separate identity game below. Actual auxiliary information must be specified consistently; the identity guarantee would require reassessment if additional information destroyed its uniform prior.

## Identity ceiling from a separate explicit finite experiment

The identity game asks which of 100 candidate people owns a designated anonymous target record. Conditional on the recipient's stipulated side information, these candidates are equally likely. Under the 100 possible assignments, the complete record multiset is the same; only ownership labels are permuted. The output law depends on the count, which these permutations leave unchanged. The owner is independent of the demand regime and mechanism randomness under this conditional law.

For either bit output, Bayes' rule cancels the identical likelihoods and leaves each candidate's posterior at **1/100 = 1%**, below the stipulated **5%** tolerance. The same holds for `(B,B)`.

This is a direct finite-experiment identity proof, not a generic inference from differential privacy to identification risk. It fails to apply if a recipient has distinguishing auxiliary information, target-linked outputs, nonuniform conditional candidate probabilities or a different record-assignment law. It establishes the maximum posterior success within this exact game; it is not a population-wide re-identification claim.

## Exact synthetic utility

For usefulness only, define a finite data-generating law. Let a regime bit `G` be equally likely to be zero or one. The 10,000 background people contribute exactly 4,000 ones when `G=0`, and exactly 6,000 ones when `G=1`. The target has independent fair presence and attribute bits `M` and `A`, and contributes `M*A`. Thus `S = C_G + M*A`. The background and target variables are independent conditional on `G`, and `G` is independent of the target's bits. These deliberately separated regimes are an assumption, not an observed empirical regularity.

The future population demand label `Z` equals `G` with probability `9/10`, independently of the mechanism draw conditional on `G`. The model predicts `B`. For each possible `(G,M,A)`, its probability of selecting the correct regime is at least

`p_min = r^999/(1+r^999) > 9999/10000`.

The minimum occurs at `G=0, M=1, A=1`, where `S=4001`. Conditional expected forecast accuracy is therefore at least

`1/10 + (4/5)*p_min = 0.899961450686... > 8999/10000`.

The exact mean over the eight equally likely `(G,M,A)` cells is `0.899961831872...`. The stated result **greater than 89.99%** is conservative and exceeds the example's **75% expected-accuracy** requirement. Before the original private source is released, `Z` is marginally balanced, so the best fixed forecast has expected accuracy **50%** under the stated baseline information.

This utility gate is expressly about the randomized procedure's ex ante expected performance under a known synthetic law. It is not the previous hold case's empirical confidence lower bound, and it is not a guarantee that every draw selects the correct model. In fact, each selected constant model has future-label accuracy 90% when it matches the regime and 10% otherwise; the probability of selecting the correct one exceeds 99.99%. A real fitted model would need an independently justified utility certificate and a clearly chosen performance criterion.

## Outcome and reproducibility

All three specified threats clear and the expected-utility requirement passes. Within this illustrative contract, the accountable authority can approve the exact cached model and the gateway can activate its limited interface. No actual agency authorisation is claimed.

Run `python verify_constructive_example.py` using Python 3.10 or later. The verifier uses only the standard library and exact `Fraction` comparisons. It checks the universal mechanism identities, rational privacy limits, the identity Bayes cancellation, every utility cell and the cached joint transcript. Decimal strings in its output are display values only; pass/fail comparisons use exact fractions. `--json result.json` optionally saves the report.

The verifier contains no dataset, stochastic simulation or empirical approval. It does not check source custody, contribution enforcement, truthful release history, production randomness or gateway implementation. The associated guide and verifier should remain together so that changing a mechanism, prior, utility law or transcript cannot silently inherit this result.
