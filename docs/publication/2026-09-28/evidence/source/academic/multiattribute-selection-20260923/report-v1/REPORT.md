# Three-to-five-attribute experiment: verified results

Development fits: 336; final fits: 108.
Records per final fit: 2,206,118; final test: 20,000.

| Attributes | Family | Omission | Equal all | Best single | Selected | Selected - equal, familywise 95% |
|---|---|---:|---:|---:|---:|---|
| 3 | logistic | 0.80358 | 0.80845 | 0.82357 | 0.82357 | +0.01513 [+0.01212, +0.01814] |
| 3 | histogram | 0.81039 | 0.81523 | 0.82975 | 0.82975 | +0.01452 [+0.01156, +0.01749] |
| 4 | logistic | 0.80242 | 0.80638 | 0.82221 | 0.82221 | +0.01583 [+0.01270, +0.01897] |
| 4 | histogram | 0.80882 | 0.81258 | 0.82833 | 0.82833 | +0.01575 [+0.01265, +0.01885] |
| 5 | logistic | 0.75644 | 0.76044 | 0.78249 | 0.78249 | +0.02205 [+0.01799, +0.02611] |
| 5 | histogram | 0.76482 | 0.76811 | 0.79009 | 0.79009 | +0.02198 [+0.01800, +0.02596] |

## Selection and limits

- k=3 logistic: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=3 histogram: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=4 logistic: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=4 histogram: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=5 logistic: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=5 histogram: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).

Development is public and disjoint from final training/test. Selection is not private for development records.
Final per-candidate bound is at most 2. Within each k, all sanitized alternatives together have bounds {'3': '23.99999999999999866773237045', '4': '29.99999999999999933386618524', '5': '35.99999999999999950039963890'}. These k values have different adjacencies; the cross-k archive is not one joint k=5 private release. The raw research archive has no DP claim.
The new final test excludes old attack/utility panels. These are fixed-record, within-2024 results with three repetitions, not all-corpus retraining or population guarantees.
Exhaustive subset search uses 8/16/32 candidates; singleton-only search needs 3/4/5. Model fitting budgets per candidate are matched, search effort across strategies is not equal.
Final fit warnings: 54; inspect results.json for all entries. Development warnings remain in the immutable selection-lock.json.
Negative and zero gains are retained. No existing-protocol superiority is established.
