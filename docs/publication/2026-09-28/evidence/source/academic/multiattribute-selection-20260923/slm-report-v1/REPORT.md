# Record-SLM three-to-five-attribute experiment: verified results

Development fits: 336; final fits: 108.
Records per final fit: 2,206,118; final test: 20,000.

| Attributes | Family | Omission | Equal all | Best single | Selected | Selected - equal, familywise 95% |
|---|---|---:|---:|---:|---:|---|
| 3 | slm_small | 0.80932 | 0.81463 | 0.82846 | 0.82846 | +0.01383 [+0.01099, +0.01668] |
| 3 | slm_medium | 0.80948 | 0.81475 | 0.82858 | 0.82858 | +0.01382 [+0.01092, +0.01673] |
| 4 | slm_small | 0.80778 | 0.81068 | 0.82581 | 0.82581 | +0.01513 [+0.01209, +0.01817] |
| 4 | slm_medium | 0.80785 | 0.81098 | 0.82563 | 0.82563 | +0.01465 [+0.01156, +0.01774] |
| 5 | slm_small | 0.76372 | 0.76763 | 0.78851 | 0.78851 | +0.02089 [+0.01708, +0.02470] |
| 5 | slm_medium | 0.76409 | 0.76769 | 0.78849 | 0.78849 | +0.02080 [+0.01691, +0.02468] |

## Selection and limits

- k=3 slm_small: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=3 slm_medium: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=4 slm_small: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=4 slm_medium: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=5 slm_small: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).
- k=5 slm_medium: selected [[0], [0], [0]]; best singleton [[0], [0], [0]] (indices: degree, married, SEX=2, Hispanic, hours>=35).

Development is public and disjoint from final training/test. Selection is not private for development records.
Final per-candidate bound is at most 2. Within each k, all sanitized alternatives together have bounds {'3': '23.99999999999999866773237045', '4': '29.99999999999999933386618524', '5': '35.99999999999999950039963890'}. These k values have different adjacencies; the cross-k archive is not one joint k=5 private release. The raw research archive has no DP claim.
The final test is shared with the CPU subset study and excludes the historical attack/utility panels. These are fixed-record, within-2024 results with three repetitions, not all-corpus retraining or population guarantees.
Exhaustive subset search uses 8/16/32 candidates; singleton-only search needs 3/4/5. Model fitting budgets per candidate are matched, search effort across strategies is not equal.
Final fit warnings: 0; inspect results.json for all entries. Development warnings remain in the immutable selection-lock.json.
Negative and zero gains are retained. No existing-protocol superiority is established.
