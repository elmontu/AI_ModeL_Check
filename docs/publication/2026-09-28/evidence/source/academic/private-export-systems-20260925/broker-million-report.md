# Public-synthetic committed-channel prototype benchmark

Lower Brier loss is better. Predictors are learned marginal probabilities, not general classifiers.
Stationary public data and predeclared shifted public data are separate controls; neither is selected using test labels.
The theorem optimizes uniform-input reconstruction, not this nonuniform predictive loss.

| n | New tasks | Repetitions | Coupled Brier | Independent joint Brier | Public stationary | Public shifted | Coupled minus independent |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1000000 | 7 | 1 | 0.210106 | 0.210109 | 0.210127 | 0.246942 | -0.000003 |

## Evidence boundary

- Public synthetic data; no agency deployment or sensitive-data validation.
- Five repetitions, where run, vary mechanism randomness on a fixed public roster and cohort.
- Every single arm is a counterfactual retained history; jointly publishing all arms is not covered by one arm bound.
- The recorded backend distinguishes standalone sampler profiling from durable broker export workflow; neither establishes an untrusted-host security guarantee.
- Each worker peak includes Python and public data as well as mechanism outputs; it is not isolated mechanism memory.
- Exact channel verification and recipient-process replay are recorded for every arm.
- Timing is descriptive for this machine. No claim of improvement over production DP systems.
