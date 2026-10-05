# Red-team evidence for export review

This milestone adds a local operational screen to the
[governed temporal release service](enforced-release-workflow.md), plus an offline
public-data pilot. A satisfied screen removes one blocker; it cannot establish
a privacy ceiling, mint privacy budget or authorize an agency release. The
existing accounting, authority, review and exact-byte delivery checks remain
mandatory.

## Run the public pilot

Use the [console environment](pipeline-quickstart.md) from this repository.
The example uses the bundled scikit-learn breast-cancer data and needs no network.

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_red_team demo --output .local/red-team-pilot-v1
```

On Linux/macOS substitute `./.venv-pipeline/bin/python`. Choose a new output
directory on each run; the command refuses to replace existing results.

| File | Content |
| --- | --- |
| `plan.json` | Public-data hash, seeds, train/holdout and calibration/audit plan, controls, stopping rule and thresholds frozen before fitting |
| `candidate.json` | Inert StandardScaler and GaussianNB parameters, feature names, public-data lineage and runtime versions |
| `policy.json` | Required tool identity, artifact/interface/data bindings, controls, resource limits, thresholds and validity window |
| `report.json` | Bound tool outcome, audit metrics, controls, counts, resource declarations and timestamps |
| `evaluation.json` | Recomputed operational status and blocking reasons |
| `reviewer-receipt.json` | File hashes, reload error, utility, target/control details and limitations |

Training fits preprocessing on training records only. The runner reloads the
saved JSON bytes, verifies prediction equivalence, and scores members and
nonmembers through that reloaded model. A fixed split keeps attack calibration
separate from audit. A known-leak row-memorizing predictor and a constant-output
null predictor exercise the same probability/scoring path. These controls test
this attack harness; they do not prove comprehensive attack coverage.

The AUC limits are illustrative local screening criteria fixed before outcomes.
Membership screening compares the stronger of AUC and its inverse, so a reversed
membership signal cannot pass by reporting an AUC below chance.
A full-artifact recipient can mount attacks beyond the single probability-loss
screen here. The pilot does not run extraction, attribute inference, poisoning,
robustness or language attacks, and the public package is not a DP-trained model.

Re-evaluate against the exact saved candidate:

```powershell
& .\.venv-pipeline\Scripts\python.exe -m model_release_assurance.export_red_team evaluate --policy .local/red-team-pilot-v1/policy.json --report .local/red-team-pilot-v1/report.json --artifact .local/red-team-pilot-v1/candidate.json
```

Exit status is 0 for a satisfied operational screen, 1 for a blocked result,
and 2 for invalid input or a runtime error. Editing even whitespace in the
candidate changes its hash and blocks evaluation. Expired policy or stale
report also blocks; results must not be reused indefinitely.

## Tool discovery

Console `GET /api/red-team-tools` returns `red-team-discovery/1`. MCP
`list_red_team_tools()` includes the same inventory under `discovery` while
preserving its existing typed `catalog` and digest. There are 25 entries:
11 classifier tool groups, three regression groups, nine language probes,
one public export screen and one separate multi-shadow experiment, with the
two language controls listed separately.

Entries describe implementation/version/source hashes, applicability,
interfaces, inputs, dependencies, report locations and evidence role. Discovery
does not load models, contact Ollama or verify optional dependency installation.
The multi-shadow script requires a source checkout; an installed wheel reports
its absence explicitly. SACRO-ML, ART, garak and PyRIT adapters are listed as
unintegrated extension points. They are not installed or executed by this change.

## Configure the temporal service

The service still requires a separately initialized and valid operator registry.
This pilot does not create one or import its GaussianNB package into one.
For a genuinely registered candidate, the trusted operator must approve a
policy covering those exact bytes, the supported recipient interface and its
actual evaluation data/split identity before accepting its report.

Before starting the service, add these fields to the corresponding existing
model entry in the operator's `workflow.json`:

```json
{
  "model_id": "EXISTING_REGISTERED_MODEL_ID",
  "red_team_dataset_sha256": "EXACT_EVALUATION_DATA_AND_SPLIT_SHA256",
  "red_team_policy": {"schema_version": "export-red-team-policy/v1"}
}
```

This is a field-location sketch, not a valid complete policy: insert the full
validated policy object with artifact hash, `recipient_interface: full_artifact`,
its descriptor hash, dataset hash, aware timestamps, age limit and all required
tool identities, controls, resource limits and metric thresholds. Retain the
model entry's other fields. The data hash identifies attack evaluation data
and splits; it is distinct from the protected-training registry dataset ID.
Use the contract in
[`export_red_team.py`](../src/model_release_assurance/export_red_team.py) as the
field reference. The initial required profile accepts only `model_only`
registrations delivering the full artifact. Cached/fresh scoring routes require
further interface-specific implementation and remain blocked in required mode.

The service pins inventory identity when opened. Changing a policy is a trusted
configuration operation requiring restart and a new matching report. Any change
to `workflow.json` changes the inventory identity for all checked requests, so
their checks/review become stale. A committed request cannot be rechecked or
have its report replaced; prepare a new request against the current ledger.
Uploading a report never changes the policy.
The default mode requires screening, so missing policy blocks progression.
For historical teaching fixtures only, a trusted operator can explicitly set
`"red_team_mode": "legacy_unassessed"` at the inventory root. Models without a
policy then show an unassessed legacy state. Supplying a policy still enforces
it. This mode is not a passed red-team result and must not be presented as one.

## Attach, review and deliver

1. Prepare a request for an existing registered model.
2. Use **Attach a red-team report** in the release page, or POST same-origin
   JSON to `/api/temporal/red-team` with `request_id` and the complete `report`
   object. The endpoint accepts at most 2 MiB and rejects extra fields,
   duplicate JSON keys and nonfinite numbers.
3. Run server checks. Required tools must be present and completed, with exact
   policy/artifact/interface/data/implementation/control identities, sufficient
   samples, valid controls, in-budget resource declarations, matching metrics,
   satisfied thresholds and current policy/report times. Failed or unsupported
   tools remain visible blockers. A caller cannot supply a `passed` flag.
4. Record the local review bound to the resulting check digest, then commit.
   Missing or failing evidence blocks direct endpoint calls as well as the UI.
5. Download through the controlled endpoint. It checks the same report again;
   expiry after commitment denies delivery without refunding privacy spending.

Replacing a report before commitment invalidates previous checks and review.
Identical reattachment is idempotent. A committed request's report is immutable;
changed evidence requires a new request and review. Report identities and
attachment events are retained in the operator database with the workflow audit.

## Production delivery plan

The [agency private-cloud production plan](production-private-cloud-plan.md)
places this local milestone within a deployment backlog: governed identity,
isolated workers, authentic evidence, protected custody, atomic registry,
external rollback detection, controlled delivery and operational acceptance.
External adapters and broader interfaces are admitted one profile at a time.

## Trust and remaining work

Reports are accepted from the trusted local operator. Hashes bind content; they
do not authenticate an external worker or prove that reported metrics, clocks,
resource use or dataset identities were honestly measured. The native pilot
executes its declared local screen, but uploaded reports have no isolated-worker
signature. Protected storage, authenticated roles, sandboxed workers, attested
resource enforcement and control of every export path remain deployment work.
Core administrative CLI/database access is outside the HTTP gate.

This operational contract is separate from the
[scientific attack-battery assessment contract](sacro-ml-red-team.md#policy-bound-assessment-integration).
Exploratory console results cannot be relabelled as validated battery evidence.
Both policy/report and evaluation retain `can_clear: false` and
`authorization_eligible: false`. Realistic multi-attack coverage, broader
recipient interfaces, external framework adapters and a justified protected
training-to-export bridge remain on the
[fine-grained plan](government-academic-separation-plan-2026-10-01.md).
