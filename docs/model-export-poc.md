# Repeated model export: executable POC

This government implementation exercise is a single-host test deployment using a fixed public synthetic fixture, not a completed agency pilot. It implements a narrow model-export path motivated by repeated-release research. It does not reuse the educational console's unrestricted evidence-download endpoints. The executable service and its tests are included in this checkout; the revised manuscript and historical research archives are maintained separately.

## Relationship to the audit console

The [government audit guide](government-audit-guide.md) covers the agency review workflow. The repository also contains an executable FastAPI console, SQLite job queue and public-data training runners. Those runners fit ordinary models and collect attack evidence; they do not provide this lab's DP construction. The lifecycle reference has transaction controls but does not deliver model bytes, and its integer counters are not a DP accountant.

The entry point is `mra export` or `python -m model_release_assurance.export_poc`; newly installed packages also provide `mra-export`. The HTTP service uses the existing FastAPI/Uvicorn runtime. The producer accepts no agency records, uploaded models, client-supplied privacy certificates or privacy-noise seeds. CLI filesystem paths select local history and output files; the MCP inspector accepts model text for structural diagnostics only.

## Run the test deployment

The website's main page now opens the [enforced release workflow](enforced-release-workflow.md),
with preparation, persisted checks and recorded review before commitment.
Verified ACS release histories are optional, separately retained research inputs; they are not bundled with this government implementation.
This older two-stage synthetic lab remains at
`http://127.0.0.1:8767/synthetic`. Its database, API routes and historical
releases remain separate from the temporal workflow.

Install the [console dependencies](pipeline-quickstart.md) once with `python scripts/setup_pipeline.py --profile console`. From the repository root, use the resulting environment's Python. In PowerShell:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc serve --data .local/model-export-poc --port 8767
```

The launcher binds **127.0.0.1 only**. Open `http://127.0.0.1:8767/synthetic` for
this exercise. It uses a separate database and never migrates the existing
console queue or historical results. Stop the foreground server with Ctrl+C;
restart with the same data directory to retain the history. The current
operator's chosen data directory is local runtime state and is not included in Git.
A new directory creates a separate synthetic test, never a new privacy
allowance for the same real population.

1. Prepare the first model. Its bytes remain internal.
2. Commit it. The broker checks the current history and commits the model and privacy state atomically.
3. Download the committed JSON model and evaluate it on the fixed public synthetic holdout.
4. Choose a second construction, prepare and commit the updated model.
5. Re-download to check identical bytes. Stop distribution to test revocation: earlier disclosure and its privacy accounting remain recorded.

The two exported artifacts are small fitted Bernoulli demand models with one probability per public group. They can be used by looking up a group's probability in `model.probabilities`. They are not neural networks or claims of broad model-family performance.

## DP protocol and operator tools

The lab begins with the protected adjacency and cumulative epsilon, then distinguishes three protocol paths:

| Protocol path | Implemented action | Accounting |
|---|---|---|
| Reuse protected information | Retrieve the latest nonrevoked committed model, byte for byte; no retraining | No additional privacy cost; retain the existing bound |
| Extend a joint release | Choose retained-state response or independent randomized response for the second model | Retained state uses a complete-history joint certificate. Independent response uses sequential composition. Both bound this two-stage history by epsilon = ln(4) |
| Train from private data | Fit a group forecast from geometric-noised second-period counts | Sensitivity-one count protection plus sequential composition; no general trainer or DP-SGD adapter |

The initial randomized-response model has epsilon = ln(2); delta is zero throughout. These are contribution bounds for the fixed adjacency, not inference-risk percentages. The retained-state second step must not be described as an independent epsilon = ln(2) mechanism. All candidate routes operate on the same fixed public synthetic fixture; there is no new-dataset ingestion. After the first stage, the UI initially selects the central-count comparator, which performed better in the retained diagnostic. That result is specific to this task.

Use the existing runtime below if executable entry points have not been regenerated. No package reinstall is required for module commands:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc catalog
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc status --data .local/model-export-poc
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc plan --data .local/model-export-poc --route central-count
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_poc verify-history --data .local/model-export-poc
```

For a new synthetic CLI exercise, `mra export init --data PATH` requires a new or empty directory. Then use `prepare --stage 1 --route first --request-id first --expected-revision 0`, followed by `commit --request-id first --expected-revision 0`, supplying the same `--data PATH`. The receipt supplies the release ID for `download --release-id ID --output NEW_FILE`, `evaluate --release-id ID`, and `revoke --release-id ID`. Prepare stage two against the current revision with one of the three implemented constructions. Download refuses to overwrite any existing file. Idempotent prepare and commit retries retain the existing draw and receipt.

`status`, `plan` and `verify-history` require existing history and do not initialize, migrate or change its source files. Read-only diagnostics copy a bounded, twice-identical database/WAL snapshot into a temporary directory and let SQLite recover that copy. Concurrent mutation may require a retry; the report can become stale immediately. This is not an atomic hostile-writer snapshot or external anti-rollback mechanism. Producer operations separately validate the live database within transactions.

The HTTP discovery and planning endpoints are `GET /api/capabilities`, `GET /api/plan?route=...` and `GET /api/history/verify`. A plan's `ready` field means the snapshot's stage permits the action, not that the model meets utility, institutional or production requirements. The general console exposes the same inert catalog at `/api/export-capabilities` and links to the separate lab; its job artifact endpoints do not deliver the export store. The [MCP tools](rag-mcp.md) expose catalog, bundle inspection, history verification and planning only. They cannot prepare, commit, download or revoke exports.

The model inspector hashes the exact supplied UTF-8 bytes and applies the strict schema. It explicitly does **not** attest training provenance or DP correctness. No attack score, catalog entry, source hash or successful diagnostic substitutes for the mechanism argument.

## Workload and privacy contract

The fixture has eight fixed public groups and 64 synthetic citizens per group. Each citizen contributes two private-modelled binary values: use of a service in period one, and use in period two. Public group and roster membership do not change between neighboring datasets. Replacing both bits of one citizen is the protected adjacency. There are exactly two releases; variable participation, arbitrary attributes and an unbounded horizon are unsupported.

The first model is fitted solely from randomized responses to the first bit with ratio 2. Its certified history bound is epsilon = log(2), delta = 0. The second model uses one of three constructions, all with complete-history ratio 4 (epsilon = log(4), delta = 0):

| Construction | What the second trainer receives | Privacy argument |
|---|---|---|
| Retained state | Protected period-two responses from the exact joint mechanism | The saved two-bit proof: truth probability 4/5 when the first response was truthful, otherwise 3/5 |
| Independent | Fresh randomized responses with ratio 2 | Composition with the fixed ratio-2 first channel |
| Central count | A protected count of period-two use for each public group | Integer two-sided geometric mechanism with ratio 2, composed with the first channel |

For the central-count route, changing one citizen's second bit changes the vector of counts by at most one in L1 because their group and participation are fixed. Noise is the difference of two independent geometric variables with success probability 1/2. Its mass is proportional to `2**(-abs(k))`, giving a likelihood ratio at most 2 for a unit count shift. Moving citizens between private groups would require a different analysis. This is a strong task-specific comparator, not a variant of the retained-state theorem.

The trainer fits its group probabilities from protected responses or counts and fixed public group sizes. Debiasing and clipping are post-processing. Raw records, per-citizen protected responses, retained flags and noise are absent from the model export. Privacy noise uses the operating system's random source through Python's `secrets` interface; a published deterministic fixture seed only constructs the public synthetic input.

The flag E = X XOR A, together with A, reconstructs X. Retaining this state is **not a reduction in sensitive information**. Any eventual research claim about restricted state access must establish a real execution or access constraint.

## Actual enforcement and its boundary

Prepared models and internal state are stored in SQLite. The HTTP API can return model bytes only from the committed-download method. The committed BLOB is read and hashed before response construction, avoiding a mutable path between hashing and delivery. Preparation exposes no model bytes or artifact digest. Request IDs bind to their original parameters; reuse with changed parameters fails. Transactions serialize commits against the expected history revision. A stale candidate cannot become a new disclosure. A retry of a committed operation returns the existing receipt and artifact, not fresh noise.

The database records the mechanism source fingerprint at initialization and refuses a restart with changed producer source. This is a version-consistency check, not remote attestation or protection from an administrator changing both code and stored commitments. At most 128 prepared requests are retained; existing idempotent requests remain accessible at the limit.

Revocation stops subsequent downloads through the broker. It does not recall copies or reduce the accounted ratio. The service does not reset its two-release history through an API call. Invalid routes, arbitrary uploads and unsupported third releases are rejected.

The updated broker checks cumulative accounting against committed releases and revocations, contiguous stages, receipt/candidate correspondence, the actual parent artifact, committed BLOB/state/certificate hashes and source binding before every operation. A local history-identity marker prevents accidental deletion of the database from silently starting a fresh history. A supported legacy history is validated before its first writable open adds the marker; read-only inspection does not migrate it. Deleting both database and marker, or replacing a consistent whole history, is outside this local guard.

This is a trusted local operator interface, not authentication or institutional authorization. The HTTP process owns its SQLite database. Logical separation of internal and exported values is implemented; independent worker identities, operating-system isolation, external anti-rollback checkpoints, hostile-administrator resistance and agency identity integration are not. SQLite crash/transaction tests do not establish protection against replacing the whole database with an old copy. Requests already admitted before revocation may finish delivering their committed bytes.

No claim is made about absolute attribute-inference risk under arbitrary auxiliary knowledge. The mechanism's DP contract is a contribution bound. There is no data-dependent utility gate in this POC: holdout metrics are descriptive and public. A future gate using private validation labels needs its own accounting.

## Research motivation and diagnostic limitations

Candidate question: **Can retaining private mechanism state improve useful successive model exports at a fixed complete-history privacy bound, under an operational constraint that existing reuse, private training and accounting do not already resolve?**

This is still a research hypothesis. [Sage (SOSP 2019)](https://arxiv.org/abs/1909.01502) already addresses cumulative leakage and quality control across exported models. [PrivateKube (OSDI 2021)](https://www.usenix.org/conference/osdi21/presentation/luo) treats privacy as a nonrenewable scheduling resource. A browser, transaction log and standard post-processing proof do not by themselves distinguish this work.

The first diagnostic compares retained-state and independent response mechanisms, a central-DP count model, and reuse of the first forecast without new private input. Each alternative is matched to the same first protected realization where applicable. Multiple alternatives are evaluated only because this fixture is public; their combined disclosure on private records would require further accounting. A ratio-4 guarantee for each alternative history is not a ratio-4 guarantee for all alternatives together.

Repeated sanitizations measure algorithm randomness on one fixed synthetic population. They are not independent populations or field trials. The held-out fixture tests downstream forecasting separately from the exact 11/15 protected-answer accuracy. If the central-count baseline wins, preserve that result and narrow the research claim. Do not choose a worse baseline merely to obtain a positive result.

The next research gate is an observed workload constraint plus a useful result beyond the strongest applicable comparator. A real agency deployment would then require a named environment, approved data path and enforcement appropriate to that environment; none is inferred from this public-data POC.

## Verification

```powershell
& .\.venv-pipeline\Scripts\python.exe -m unittest discover -s tests -p 'test_export_poc*.py' -v
```

The tests exercise exact channel constraints, trainer/export information boundaries, uncommitted access, tampering, stale and concurrent commits, crash/retry behavior, persistent history, revocation, protocol plans and CLI/API/MCP adapter boundaries. Current government implementation checks are indexed in the [retained verification record](../reproduction/government-audit-update-20260922/README.md); runtime state stays under `.local/`.

Optional historical research resources are retained separately at `academic/export-poc-20260920/` and `academic/implementation-tools-20260921/`, including the older source bytes under the latter directory's `before/` subdirectory. They are not included in this government publication. The old study verifier pins its vintage source hashes: changed broker/UI files intentionally fail that source comparison, and its old hashes must not be replaced. Current unit tests validate implementation behavior; they are not a rerun of the historical utility study, a universal DP proof, production custody or an agency pilot.
