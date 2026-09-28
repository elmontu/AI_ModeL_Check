# Larger-training diagnostic

200,000 public training rows; original HGB configuration and scored populations retained.
Protocol, thresholds, privacy caps and scoring caches unchanged. Adaptive exploratory comparison, not new certification.

| Input | Task | Final accuracy | Final AUC |
|---|---|---:|---:|
| omit | income | 0.70270 | 0.75727 |
| omit | degree | 0.65225 | 0.67597 |
| omit | married | 0.61470 | 0.64616 |
| raw | income | 0.73560 | 0.80540 |
| raw | degree | 0.65670 | 0.68922 |
| raw | married | 0.64925 | 0.69730 |
| equal-2 | income | 0.70460 | 0.76220 |
| equal-2 | degree | 0.65400 | 0.67641 |
| equal-2 | married | 0.61705 | 0.65107 |

Raw inputs are non-private diagnostics, not release candidates. These learners do not establish an information-theoretic ceiling.
All nine models and 36 score vectors independently checked; first 1024 final scores reconstructed exactly.
