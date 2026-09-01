# Software architecture

> **Status: Reference.** This document describes the complete repository architecture and its
> production integration boundary. It does not create a model-release authorization.

## Purpose, scope, and sources of truth

Model Release Assurance (MRA) has an offline, fail-closed Python core for validating release
contracts, assessing source-bound evidence, selecting among submitted release configurations, and
replaying certificates and Model Release Assurance Protocol (MRAP/1.0) transcripts. Optional
evidence-lab workers may execute local model code, download public datasets, or launch subprocesses;
they are experimental and are not part of the supported offline core.

MRA produces reports, manifests, certificates, and replay results. It does not train, export, deploy,
serve, authorize, suspend, or revoke production models. The canonical repository boundary is defined
in [Project scope](project-scope.md).

```text
Legend: [I] implemented supported/reference component
        [E] implemented experimental component
        [X] external adopter-owned production component
```

When sources disagree, use the following precedence:

| Concern | Source of truth | Boundary |
|---|---|---|
| Protocol roles, states, gates, and authority | [MRAP/1.0](model-release-assurance-protocol.md) | Normative protocol specification |
| Contracts accepted by the current runtime | Pydantic models under `src/model_release_assurance/` | Executable validation semantics |
| Machine-readable contracts | [`schemas/`](../schemas/) and its [schema map](../schemas/README.md) | Current exports plus explicitly retained compatibility schemas |
| Formal claims | [`formal/lean/`](../formal/lean/) and [formal verification](formal-verification.md) | Proofs about the scoped Lean model, not the Python runtime or a deployment |
| Repository ownership and support | [Project scope](project-scope.md) | Canonical product and non-goal boundary |
| This document | `docs/architecture.md` | Descriptive map of the above components |

## Reference deployment architecture

The system has three operational trust planes and one side access surface. Training, export, assessment, and
serving are lifecycle stages across those planes, not independent sources of authority. MCP is an
integration mechanism beside the assurance plane; it is not the governance plane.

```text
[X] RELEASE, POLICY, POPULATION, AND EVIDENCE ROLES
      | frozen JSON contracts, regular-file artifacts, source-bound evidence
      v
1. EVIDENCE / MODEL-EXECUTION PLANE
┌─────────────────────────────────────────────────────────────────────────────┐
│ [X] Approved isolated evidence workers + immutable evidence/artifact store   │
│ [E] Local research workers emit measurements, attack floors, or screens      │
│     that require approved binding or recollection before assessment          │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ inert referenced files
                                   v
2. OFFLINE ASSURANCE / CHECKING PLANE
┌─────────────────────────────────────────────────────────────────────────────┐
│ [I] `mra` CLI / Python core                                                  │
│     contracts -> integrity checks -> local analyzer services -> decisions    │
│     -> assessment / optimization / certificate / replay outputs              │
│ [I] local intent/terminal SQLite AuditStore for audited CLI operation        │
│ [I] supplied MRAP transcript verifier                                        │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ recommendations and replayable records
                                   v
3. MRAP GOVERNANCE / WORKFLOW / ENFORCEMENT PLANE
┌─────────────────────────────────────────────────────────────────────────────┐
│ [X] authority submits -> portfolio registry performs atomic CAS -> AUTHORIZED│
│ [X] deployment gateway verifies live artifact/interface/lease -> ACTIVE      │
│ [X] monitoring and incident authorities -> continue/suspend/revoke/expire    │
└─────────────────────────────────────────────────────────────────────────────┘

SIDE ACCESS SURFACE
[E] MCP-compatible reviewer host <-> JSON-RPC/stdio <-> local MRA MCP server
    -> advisory retrieval, validation, audit-chain reads, and experimental
       non-authorizing runners; no signing, registry, activation, or failover path
```

Only an external atomic portfolio-registry commit can create `AUTHORIZED`. Only an external gateway
that rechecks the exact live artifact, interface, controls, expiry, and lifecycle state can create
`ACTIVE`. The repository can replay declarations of those events; it does not operate them.

## Runtime units and process topology

| Runtime unit | Status and process | Responsibility | Important non-claim |
|---|---|---|---|
| `mra` CLI and Python package | **[I]** One local Python process | Parse contracts, assess evidence, optimize candidates, export schemas, generate/verify signatures, and replay certificates and transcripts | Not a daemon, scheduler, registry, gateway, or authorization service |
| Default analyzer registry | **[I]** In the same process as the core | Route each typed analyzer input to exactly one local analyzer and return `EvidenceRecord` values | The default analyzers are not Kubernetes microservices and do not authenticate an external worker identity |
| `AuditStore` | **[I]** Local SQLite file opened by the CLI | Append assessment/optimization intent and terminal events to a hash chain; replay it and export a head/count checkpoint | Not an immutable evidence store, telemetry database, MRAP transcript, externally anchored transparency log, or authoritative ledger |
| MRA MCP server | **[E]** Separate local source-checkout process | Expose tools over stdio for retrieval, validation, read-only audit verification, and experimental runners | No resources, prompts, HTTP/SSE transport, analyzer RPC endpoints, or lifecycle authority |
| Evidence-lab workers and scripts | **[E]** Trusted local process or subprocess | Run bounded model, privacy, red-team, OpenML, XGBoost, portfolio, and strategic experiments | Measurements are not automatically admissible assessment evidence and never authorize |
| Lean package | **[I] build-time** Separate Lake/Lean build | Define and prove properties of the abstract MRAP model | Not loaded by the Python runtime and not a refinement proof for Python or infrastructure |
| GitHub/Make automation | **[I] repository automation** CI or maintainer process | Compile, test, replay schemas/links/proofs, build and smoke-test distributions, create draft releases | Does not publish to a package index or deploy MRA as a service |
| Production identity, storage, registry, gateway, orchestration, and monitoring | **[X]** Adopter-owned services | Authenticate roles, isolate workers, store immutable artifacts, commit authorization atomically, enforce serving, and operate incidents | Specified as integration obligations, not implemented here |

The current component dependency shape is:

```text
ENTRY SURFACES
  `mra` CLI -----------+
  documented imports --+----> SUPPORTED CORE
                       |       contracts/models
                       |          |
                       |          +-> assessment engine -> service registry
                       |          |                         -> local analyzers
                       |          +-> optimizer -> decision theory / portfolios
                       |          +-> protocol and certificate verifiers
                       |          +-> integrity / signatures / local AuditStore
                       |
  MCP stdio server ----+----> EXPERIMENTAL TOOL SERVICE
                               -> in-memory docs/schema knowledge index
                               -> validation and read-only audit helpers
                               -> experimental workflows / privacy subprocess

  scripts ------------------> EVIDENCE LAB / BENCHMARKS
  Lake/Lean ----------------> FORMAL MODEL (build-time, separate boundary)

FILESYSTEM ADAPTERS
  JSON contracts + referenced files + deployable artifact + PEM keys
  -> generated JSON reports/certificates/manifests + optional SQLite audit DB
```

`McpAnalyzerService` and the current MCP server are different components. The former is an implemented
caller-supplied transport adapter for a prospective remote analyzer envelope; no remote analyzer is
registered by default. The latter is the local reviewer tool server in `mcp_server.py` and does not
host the prospective `analyze_*` tools used by that adapter.

## Supported and experimental entry points

### CLI command families

| Family | Commands | Output or effect |
|---|---|---|
| Contract and assessment | `validate`, `model-coverage`, `assess` | Structure validation, advisory family coverage, or scoped `AssessmentReport 4.0`; governance-grade use records intent and completion/failure in a local audit chain |
| Release selection | `optimize` | `OptimizationReport 3.0`; governance-grade use records intent and completion/failure in a local audit chain |
| Portfolio statistics | `portfolio-multinomial-generate`, `portfolio-multinomial-verify`, `portfolio-multinomial-compile` | Simultaneous evidence or an incomplete-portfolio problem |
| Portfolio certificates | `portfolio-solve`, `portfolio-verify` | Exact/envelope `AnalyticPortfolioEvidenceEntry 1.1` and replay result |
| Protocol design | `protocol-solve`, `protocol-verify` | Finite soundness/liveness certificate and exact replay result |
| Lifecycle replay | `release-protocol-verify` | Structural or authenticated verification of a supplied `ReleaseProtocolRun 1.1`; optional machine result records the exact profile and skipped checks |
| Integrity | `keygen`, `sign`, `verify`, `optimize-sign`, `optimize-verify`, `audit-verify`, `audit-checkpoint` | Local PEM keys, signed manifests, structured chain verification, and an externally anchorable ledger head/count |
| Schema export | `schema` | One current generated JSON Schema selected by `--kind` |

The versioned contracts and CLI are the supported product surfaces. `__init__.py` exposes documented
Python conveniences, but an internal module is not automatically a stable public API because it can
be imported. Scripts are repository-root utilities, not console APIs. The experimental MCP surface is
documented separately in [Advisory retrieval and MCP integration](rag-mcp.md).

`model-coverage` is a separate advisory review over the governed 20-family catalog. It is not invoked
by `AssuranceEngine.assess`, and catalog coverage never clears a release.

## Training-to-serving lifecycle: external integration profile

```text
1. TRAIN / COLLECT [X]       2. EXPORT / FREEZE [X]       3. ASSURE [I]
controlled training           checkpoint + tokenizer       AssessmentRequest 4.0
+ declared instrumentation    + preprocessing/config        for final bundle
+ minimized observations      + exporter/runtime/precision  -> AssessmentReport 4.0
+ early health or             -> complete deployable bundle -> optional selection
  adopter-policy screens      -> artifact SHA-256
             |                          |                         |
             +--------------------------+-------------------------+
                                                                  v
4. AUTHORIZE [X] -> authority submits -> registry performs CAS -> AUTHORIZED
                                                                  |
                                                                  v
5. SERVE / MONITOR [X] -> gateway exact-binding check -> ACTIVE
   -> minimized monitoring evidence -> continue / suspend / revoke / expire
```

The release gate belongs after export. A checkpoint may be upstream provenance and an early gate may
stop promotion, but neither is the release artifact. TorchScript, ONNX, TensorRT, quantization,
tokenizer, preprocessing, wrapper, dependency, runtime, or precision changes may change bytes,
behavior, and the served interface.

The current core checks only that `ReleaseContract.artifact_path` resolves to one regular file, that
its bytes match `artifact_sha256`, and that the request contains a valid declared `InterfaceContract`.
It does not inspect an archive/package or prove it is complete. This makes package-to-gateway identity
the critical integration obligation: the external assembler must create a deterministic bundle
manifest enumerating every weight/shard, tokenizer, pre/postprocessor, configuration, wrapper,
dependency, runtime, precision/calibration file, and entry point; the gateway must verify that manifest
and the exact same outer bundle digest before activation. Rechecking only an unpacked model file, or
trusting filenames inside a tar/zip, is insufficient. A model card is supporting documentation, not a
release contract or clearance evidence.

The optimizer's `GarblingCertificate` is a narrow finite-information-experiment transfer mechanism.
It is not a binary export-equivalence certificate and does not replace new artifact, interface,
utility, control, threat, or portfolio bindings. Retraining, re-export, quantization, packaging, or
interface changes therefore normally require a new digest, release instance, and assessment.

Checkpoint selection must be preregistered or covered by an approved simultaneous-selection method.
Choosing a checkpoint after repeatedly inspecting outcomes creates adaptive-selection and
multiplicity obligations. Fairness is adopter-policy-specific future evidence: the current threat and
policy contracts do not define a fairness decision, and demographic parity alone is not a complete
fairness contract.

## Implemented runtime workflows

### Validation and assessment

The `assess` CLI path below requires `--audit-db`. It reads, parses, and validates the request before
creating the audit intent; missing, malformed, schema-invalid, and direct-library attempts therefore
have no CLI intent/terminal record and remain outside governance-grade audit coverage.

```text
AssessmentRequest 4.0
        |
        +-> `mra validate`: strict Pydantic structure only
        |
        +-> `mra assess`:
              0. read, parse, and validate the request (pre-intent boundary)
              1. append an audit intent containing the canonical full-request hash
              2. load and hash-check PolicyBundle 2.0
              3. compare policy identity, validity, mandatory threats, tolerances, and required analyzers
              4. reject producer versions below policy or unaccepted implementation/configuration digests
              5. resolve the release artifact/configuration/evidence as regular files and verify SHA-256
              6. reconstruct release/policy/artifact/interface/population/game context
              7. route each discriminated input to exactly one analyzer service
              8. revalidate returned producer, analyzer/input-kind, context, and capabilities
              9. aggregate floors and complete-declared-interface ceilings per mandatory threat
             10. append exactly one completion or failure event referencing the intent
             11. emit AssessmentReport 4.0 with non-authorizing scope fields
```

The request and every returned `EvidenceRecord` carry a typed producer service ID/version plus
implementation and configuration SHA-256 digests. The engine checks them against the routed service
descriptor and `PolicyBundle.analyzer_requirements`; a policy bump can therefore reject stale
analyzers mechanically. These byte/version bindings still do not authenticate a remote workload or
prove its output truthful. Production remote services require workload identity, attestation,
authenticated transport, and request/response audit binding.

Current local analyzer semantics are fail-closed:

| Input kind | Possible decision-bearing output | Boundary |
|---|---|---|
| `tree_linkage` | Recipient-realizable exact values may block; they clear only with complete-interface coverage | Tree-ensemble linkage only |
| `dp` | Validated end-to-end mechanism ceilings may clear the assessed metric | Conditional on all deployed data/output paths being inside the proved mechanism; the core checks only the declared interface and never emits blocking DP evidence |
| `attack` | Validated empirical floors may block | Never clears |
| `controlled_inference` | Validated attribute/reconstruction floors may block | Never clears; generic path rejects interactive LLMs |
| `llm_canary` | Properly bound membership/reconstruction floors may block | Never clears; invalid collection becomes a screen |
| `llm_watermark` | Screen only | Neither blocks nor clears |
| `population` | Population-model screen only | Neither blocks nor clears |

Default service descriptors are derived from each analyzer's implemented maximum decision
capabilities: tree `(clear, block)`, DP `(clear only)`, attack/controlled inference/canary `(block
only)`, and watermark/population `(neither)`. Adapter construction rejects capability widening, and
the engine revalidates each returned record. A remote registry must still authenticate the descriptor
issuer and test the worker behavior.

### Selection and certificate pipelines

Assessment and selection are separate calls; `assess` does not automatically invoke `optimize`.
Consequently, every assessment report and signed assessment manifest says
`composition_scope=single_release_no_portfolio`, `interface_assurance=declared_interface_only`, and
`authorization_eligible=false`. A per-release `clear` cannot be represented as portfolio clearance.
`previous_release_ids` is submitter-declared lineage, not an authoritative list of active releases.

```text
AssessmentReport reference(s) + candidate artifacts/interfaces
+ utility certificates + controls + finite experiments
+ portfolio/search-space evidence + caller-supplied registry-snapshot commitment
+ active policy reference + versioned selection policy
                    |
                    v
OptimizationRequest 3.0
  -> load and bind assessment reports/manifests
  -> require the active PolicyBundle to allowlist the selection-policy digest
  -> replay source files, controls, utility, portfolio, search, and garbling claims
  -> require the complete active release set plus candidate in portfolio evidence
  -> reject stale/future registry snapshots, unsupported trust profiles, or expired inputs
  -> evaluate each fail-safe candidate gate
  -> select from the feasible Blackwell-minimal frontier using declared ordered tie-breaks
                    |
                    v
OptimizationReport 3.0 (echoes policy, registry, covered releases, selection policy, scope)
  -> separate optional `optimize-sign` -> SignedOptimizationManifest 3.0
```

The supported trust profiles are `cooperative` and `separated_assessor`; the latter requires a valid
signed assessment manifest and accepted signer-key ID. A signature establishes bytes/key provenance,
not truth. It also does not authenticate the registry snapshot, utility, controls, search-space,
experiment, transfer, or portfolio objects used at selection. The optimizer checks internal
candidate-plus-declared-active-set consistency; only an external authenticated live registry can
establish complete composition. An adversarial-supply-chain profile is deliberately absent until independent artifact
replay, workload attestation, isolated evidence collection, managed identity, and custody controls
exist.

If no candidate is feasible, the optimizer returns `reject` only when the search space has a valid
exhaustiveness certificate; otherwise it returns `redesign_required`. A passing selection remains a
recommendation and does not mutate the external portfolio registry.

The selection policy is an exception to the otherwise caller-attested selection inputs: the
optimizer requires its canonical digest in `PolicyBundle.accepted_selection_policy_sha256s`. That
authorizes the preference ordering in-band but does not authenticate the other selection-stage
objects.

The supporting statistical pipeline is also explicit rather than implicit:

```text
sampling plan + raw multinomial counts + error budget
  -> simultaneous multinomial evidence
  -> portfolio specification + compiler
  -> incomplete-portfolio problem
  -> exact or conservative envelope certificate
  -> independent replay
```

The finite protocol-feasibility solver and the exact-rational strategic-assurance module are design
and stress-test tools. Their certificates do not override assessment, selection, or MRAP gates.

### Integrity, audit, and lifecycle replay

- Assessment and optimization signing use separate Ed25519 manifest contracts over canonical MRA
  JSON. Signatures establish byte/key binding, not evidence truth, institutional authority, or safety.
- For successfully parsed/validated assessment/optimization requests, `AuditStore` appends an intent
  containing the canonical full request, release/instance identity and hash before analyzer/optimizer execution, then exactly
  one completion (including the canonical report and hash) or failure event referencing that run.
  New events use a domain-separated hash that binds the ledger and release instance. SQLite uses
  `BEGIN IMMEDIATE`, WAL mode, and `synchronous=FULL` for each append. External anchoring and a
  canonical institutional ledger namespace remain required.
- `release-protocol-verify` replays event order, actor roles, artifact kinds and declared hashes,
  checks artifact files unless explicitly skipped, and verifies lifecycle
  transitions, exact `+1` portfolio sequence, the release-bound `MRAP-STATE-1` head recurrence, CAS
  declarations, and deployed bindings. The supplied portfolio-commit digest is a cryptographic
  commitment; replay does not prove its semantic completeness or authoritative registry inclusion.
  `structural_v1` permits
  unsigned declarations; `authenticated_v1` additionally checks release-bound event and artifact
  signatures against a supplied trust store and compromise list. `ReleaseProtocolVerification 1.0`
  embeds the run hash, verification time, runtime identity, profile, artifact/signature verification booleans,
  skipped checks, and degradations.
- The CLI requires `--audit-db`; there is no unaudited CLI mode. The completion append precedes
  report-file creation, so an append failure cannot
  leave a newly written report. An intent without a terminal event is detected as orphaned. The
  direct library path is exploratory, non-governance-grade, and non-authorizing.
- `audit-verify` validates contiguous sequence numbers, predecessor/event hashes, intent/terminal
  pairing, and optional expected ledger ID, event count, and head. `audit-checkpoint` exports those
  anchor values. Only an externally retained checkpoint makes valid tail deletion or ledger
  replacement detectable against a trusted prior state.

### Experimental MCP and evidence-lab workflows

At startup the MCP server builds a deterministic in-memory lexical index from the checkout's `docs/`
and `schemas/` trees. It then serves tools over stdio. Most tools are advisory or read-only; selected
tools can execute trusted local model code, train experimental estimators, write beneath `output/`,
populate an ignored public-data cache, or launch the named privacy virtual environment.

The MCP tool list is an API boundary, not an operating-system security boundary. Omitting lifecycle
mutation tools does not prevent the same process identity from reading PEM files or writing an audit
database it can reach; selected path-confinement checks likewise do not constrain subprocesses or
trusted model code. There is no built-in remote identity, tenant isolation, durable retry,
cancellation service, or comprehensive CPU/memory/runtime control.
Raw tensors, gradients, activations, losses, prompts, or model outputs should not become general MCP
resources. A production reviewer MCP service must run as a dedicated non-root principal with no path
to signing keys, writable audit/registry state, or deployment credentials; mount only the approved
documentation/schema corpus and a read-only audit snapshot, constrain egress, and place execution
workers behind a separate authenticated queue/service. Future privileged operations belong in a
separate authenticated operator service; MCP may at most submit a typed intent for external approval
and execution.

## Release-contract architecture

`ReleaseContract` is a nested current contract inside `AssessmentRequest 4.0`, not a standalone
top-level schema and not the complete normative MRAP release instance. It binds:

- `release_id`, owner, recipient, purpose, previous releases, and expiry;
- model family, structured task/modality/training profile, and protected unit;
- one local regular-file artifact path and its exact SHA-256 digest; and
- `InterfaceContract 2.0`: declared protocol/access, structured response/download/summary outputs,
  precision and serialization, timing, error/status/retry behavior, batching/concurrency/state,
  side/local/admin access, query budget, authentication/rate controls, and the interactive-LLM
  subprotocol where applicable.

The enclosing request adds the policy reference, population scopes, threat contracts, and typed
analyzer inputs. Each input carries source-observed hashes for the release contract, policy, artifact,
interface, population scope, and decision game plus a typed analyzer producer and configuration
binding. Workers return typed `EvidenceRecord` objects; the engine revalidates those bindings, policy
allowlist/version floor, and analyzer/input-kind capability before deciding.

`InterfaceContract` is still an interested-party declaration. The report therefore fixes
`live_interface_verified=false`; neither the engine nor the optimizer may change it. A separate
gateway conformance/activation receipt must measure the deployed bundle and prove that the declaration
covers, as applicable: labels, scores, probabilities and logits; embeddings, gradients, parameters
and downloadable files; numeric precision and serialization; error payloads and status behavior;
timing/rate/batching and cross-request state; retrieval, tools and memory; update paths; and any local
or administrative access. Differential privacy remains valid under post-processing only when every
deployed path is within the proved end-to-end mechanism.

| Boundary | Current contract | Producer -> consumer | Authority |
|---|---|---|---|
| Submission and policy | [`assessment-request-v4.json`](../schemas/assessment-request-v4.json) (`4.0`) with nested `ReleaseContract`; [`policy-bundle-v2.json`](../schemas/policy-bundle-v2.json) (`2.0`) by path/hash | External package and policy roles -> validator/engine | Defines candidate, producer allowlist/version floors, and policy context; producer digests are not workload authentication |
| Engine and analyzer | Nested `ReleaseContract`, `ThreatContract`, discriminated analyzer input, and `EvidenceRecord`; service envelope `2.0` in Python | Engine -> local analyzer or prospective MCP adapter -> engine | Analyzer emits producer-bound evidence; central engine decides; no standalone public service-envelope schema |
| Assessment output | [`assessment-report-v4.json`](../schemas/assessment-report-v4.json) and [`signed-manifest-v2.json`](../schemas/signed-manifest-v2.json) | Engine/assessor -> reviewer, optimizer, or audit store | Explicitly single-release, declared-interface-only, and non-authorizing; the signed manifest directly binds the interface digest |
| Local audit replay | [`audit-verification-v2.json`](../schemas/audit-verification-v2.json) and [`audit-checkpoint-v1.json`](../schemas/audit-checkpoint-v1.json) | AuditStore -> reviewer/external immutable anchor | Detects intent omissions and local-chain tamper relative to an anchor; not an authoritative or immutable ledger |
| Selection | [`optimization-request-v3.json`](../schemas/optimization-request-v3.json), [`optimization-report-v3.json`](../schemas/optimization-report-v3.json), [`signed-optimization-manifest-v3.json`](../schemas/signed-optimization-manifest-v3.json) | Configuration/assessment roles -> optimizer -> external authorization process | Binds active policy, portfolio registry, covered releases, and selection policy; does not commit or activate |
| Portfolio statistics and certificates | Current multinomial plan/count/budget/request/evidence, portfolio specification/problem, and certificate families | Evidence planner/worker -> generator/compiler/solver -> verifier and optimizer | Bounded statistical or mathematical support only |
| Protocol design | [`protocol-feasibility-problem-v1.json`](../schemas/protocol-feasibility-problem-v1.json) and [`protocol-feasibility-certificate-v1.json`](../schemas/protocol-feasibility-certificate-v1.json) | Protocol designer -> solver/verifier | Design-time finite-model result only |
| Governance lifecycle | [`release-protocol-run-v1.1.json`](../schemas/release-protocol-run-v1.1.json) and [`release-protocol-verification-v1.json`](../schemas/release-protocol-verification-v1.json) (protocol `MRAP/1.0`) | External MRAP roles/services -> offline verifier | Replays the declared lifecycle and records verification degradation; external registry and gateway alone create `AUTHORIZED`/`ACTIVE` |

All current and retained historical schemas are listed in the [schema map](../schemas/README.md), and
the deterministic `current-schema-manifest-v1.json` binds each current schema's exact bytes and model
registration for CI replay. That source-controlled inventory is not a protected release signature;
release signing/attestation and key custody remain external controls. The
current CLI rejects superseded assessment, optimization, portfolio-certificate, and release-protocol
versions; schema retention alone is not historical executable replay. Long-retention deployments must
preserve each released wheel, dependency lock, trust metadata, and vintage replay fixtures until a
version-dispatched verifier is implemented.

Assessment and optimization manifests are distinct from `ReleaseProtocolSignature`, which signs
domain-separated MRAP event or artifact declarations. One signature type cannot substitute for
another. Many lifecycle artifact kinds—including full registration, evidence plan/bundle,
authorization commit/receipt, portfolio commit, activation receipt, monitoring report, incident,
decommission, and abort content—have no standalone current content schema. The transcript verifier
checks their kind, relative path, digest, producing role, signature when required, and state-machine
placement; it does not semantically parse their full JSON content.

### External target-integration contract gaps

These are adopter production-program requirements, not promised schemas in the current package:

| Gap | Required bindings before implementation |
|---|---|
| Training run and checkpoint | Dataset/code/environment digests, parameters, seeds, topology, owners, stopping and checkpoint-selection policy, checkpoint lineage and digest |
| Telemetry and adopter-policy checks | Run/release identity, sequence/time, metric definition, aggregation, producer/attestation, sensitivity, payload digest/reference, retention/access, uncertainty and decision semantics; fairness additionally needs governed population/group definitions and policy authority |
| Export and release package | Source-checkpoint digest, exporter/toolchain/format/precision, calibration, tokenizer/preprocessor/wrapper/runtime/dependency identities, compatibility tests, final bundle digest and limitations |
| Privileged action | Authenticated actor, role/tenant scope, requested action, reason, approvals, idempotency, expected state/version, result, time, cancellation and audit receipt |
| Deployment and monitoring | Deployment target, authorization/activation receipts, live artifact/interface binding, monitoring plan/window/baseline, drift or incident result, lifecycle action and immutable audit references |

Adding decision-bearing training, fairness, export, or monitoring fields would require independently
versioned models, schemas, negative tests, authorization rules, and migration policy.

## Data and storage architecture

| Data or store | Owner/writer | Reader | Integrity and lifecycle |
|---|---|---|---|
| Versioned schemas, schema manifest, protocol docs, and formal artifacts | Repository maintainers through Git review | Reviewers, Make/CI replay, and MCP tools for the docs/schema subset | Committed source with deterministic current-schema digest inventory; current versus compatibility status is explicit; runtime request validation uses Pydantic models rather than reading schema files; release-signing custody is external |
| Request, policy, evidence, and release-artifact files | Caller and external evidence roles | Supported core | Caller-owned filesystem; referenced files resolve relative to the input contract, must be regular files where required, and are SHA-256 checked before use; the core never deserializes the release model binary |
| Reports, certificates, and manifests | CLI, scripts, or caller-selected Python code | Reviewers, verifiers, optimizer, external workflow | Direct JSON writes to caller-selected paths, conventionally ignored under `output/`; production use must persist request, evidence, report, manifest/receipt, audit checkpoint, and trust metadata under adopter retention/legal-hold/backup/restore controls |
| SQLite AuditStore | Required for CLI `assess`/`optimize`; library engines remain pure/non-authorizing | `audit-verify`, `audit-checkpoint`, and read-only MCP verifier | Intent/terminal WAL/FULL-sync chain; new hashes bind ledger/release/instance identity while legacy hashes require explicit opt-in; no signature, authoritative namespace, remote anchor, legal hold, replication, or authorization semantics |
| PEM keys and trust-store paths | Local `keygen` or external maintainer | Sign/verify and authenticated transcript replay | Reference filesystem key handling; no KMS/HSM, identity enrollment, rotation service, or secret distribution |
| Knowledge index | Built in memory by the MCP server; optional save/load API | MCP search tool | Deterministic lexical chunks with source and chunk hashes; no embeddings, vector database, tenant filtering, or truth authority |
| Experimental output and public-data cache | Evidence-lab workers or MCP subprocess | Researchers and replay utilities | Ignored runtime data; may contain generated models and measurements; not retained release evidence unless an external process freezes and binds it |
| Immutable artifact/evidence store, registry, and monitoring store | External production services | External authorities, gateway, monitors, and supplied transcript assembler | Required target infrastructure; not implemented or emulated by local SQLite |

The standard CLI does not sandbox caller-selected input or output paths. Experimental MCP methods add
repository-root confinement for selected calls, but that is not process isolation: execution tools and
subprocesses still inherit every file and credential permission of the MCP server principal.

## Deployment, dependencies, and release automation

### Current deployment modes

| Mode | Runtime | Scope |
|---|---|---|
| Supported core | Python 3.11+ with Pydantic and `cryptography`; installed wheel or source checkout | CLI/library validation, assessment, signing, replay, and mathematical paths that need no optional numerical dependency |
| Solver tier | `portfolio` extra with SciPy | Linear programs and statistical interval helpers used by portfolio/protocol paths |
| Experiment tier | NumPy, Pandas, PyArrow, SciPy, scikit-learn, XGBoost, and joblib | OpenML, empirical, XGBoost, stochastic, and red-team research paths |
| MCP tier | `mcp>=2,<3`, source checkout | Local stdio server; docs/schemas corpus is not bundled in the wheel |
| Privacy tier | Experiment dependencies plus PyTorch in `.privacy-venv` | Public-data CNN/LSTM/XGBoost/Transformer subprocess; may require network access |
| Formal tier | Lean toolchain pinned under `formal/lean/` | Separate proof build and axiom audit |

`ReleaseOptimizer` does not call SciPy: it replays supplied transfer certificates, computes graph
reachability, and applies the declared ordering. Optional portfolio/protocol solver and statistical
generation paths may use SciPy. Ordinary float-valued comparisons remain Python binary64 in either
case and cannot satisfy MRAP G7 at an unresolved clearance boundary.

The repository contains no Dockerfile, Kubernetes manifest, Helm chart, Terraform stack, message
broker, object-store service, telemetry database, or production server deployment. A target
microservice topology must add authentication, attestation, isolation, deadlines, cancellation,
durable orchestration, replay protection, resource quotas, and operational ownership. See the
[production roadmap](reference/production-roadmap.md).

### Build and release flow

```text
pull request / push to main / manual dispatch
  +-> Lean build and axiom audit -------------------+
  +-> Python 3.11 / 3.12 / 3.13 matrix ------------+-> package job
      compile + tests + schema/manifest replay + links   -> wheel/sdist build
                                                         -> metadata and clean-venv smoke tests

annotated vX.Y.Z tag reachable from main
  -> Lean build and axiom audit
  -> Python 3.12 release job
       require tag == package version
       run `make check`
       build and smoke-test artifacts
       create draft GitHub release
```

The automated release does not publish to PyPI or deploy a service. Ownership, licensing,
provenance attestation, credentials, rollback, and publication approval remain maintainer controls
documented in [Release process](releasing.md).

## Security, trust, and failure boundaries

| Boundary | Current control | Residual limitation |
|---|---|---|
| Contract input | Frozen Pydantic models, unknown fields forbidden, finite values and cross-field validators | Valid structure does not establish truth, identity, or authorization |
| Filesystem evidence | Strict path resolution, regular-file checks, SHA-256, exact source-field binding | Hashes detect change relative to a trusted expected digest; they do not make storage immutable or authenticate the digest issuer |
| Release binary | Core hashes one opaque regular file | Core does not safely deserialize, enumerate bundle contents, scan, execute, or prove export equivalence; assembler and gateway must verify the same complete bundle manifest/digest |
| Analyzer boundary | Unique input-kind routing, exact default capabilities, typed producer/version/configuration digests, policy floors/allowlists, and returned-context checks | Digests are not workload authentication; remote mTLS, attestation, quotas, retry, and cancellation are external |
| Decision boundary | Floors may block; only complete-declared-interface exact/ceiling evidence may clear; contradiction is distinct from absence and cannot demote an established block | Statistical/modeling assumptions and live-interface completeness still require independent approval |
| Signing keys | Ed25519 canonical manifests and protocol signatures | Filesystem PEM storage is not institutional identity or managed key custody |
| Runtime provenance | Assessment, optimization, lifecycle-verification and audit-verification outputs include deterministic package/component/source/Python/dependency/algorithm identity | The producing process reports its own identity; trusted build provenance, artifact signature, released dependency lock and independent attestation remain external |
| MCP boundary | Local stdio and a deliberately non-authorizing API surface | Tool omission/path checks do not constrain the process; production needs a separate non-root principal with no signing key or writable audit/checkpoint/governance/registry/deployment access, plus separately isolated execution workers |
| Audit boundary | Post-validation/pre-analyzer release-bound intent, exactly one terminal event, contiguous sequence/hash replay, ledger/release identity, and externally anchorable head/count | Pre-validation/direct-library attempts are absent; a caller may choose a fresh ledger and a local attacker can truncate or replace an unanchored database; canonical namespace, checkpoint custody and immutable retention are external |
| Formal boundary | Pinned Lean build, theorem inventory, axiom audit, correspondence manifest | Proves the abstract model only; Python and infrastructure refinement is unproved |

### Observability and auditability

Current operational signals are CLI stdout status/verdicts, typed JSON outputs, optional signed
manifests, the required CLI audit chain, exported audit checkpoints, and explicit replay tools.
Completed domain outcomes—including `block`, `inconclusive`, `redesign_required`, and `reject`—exit
`0`; validation/integrity/operational failures exit `2`. Automation must inspect the report rather
than treating process success as release approval. Direct library use does not silently acquire an
audit record.
Experimental reports are study artifacts, not production telemetry.

There are no structured application logs, metrics, traces, health/readiness endpoints, dashboards,
alerts, centralized operational audit service, or on-call integration. Production observability is an
external work package, not an implied property of the local audit database.

### Failure and recovery behavior

| Failure | Current behavior | Recovery owner |
|---|---|---|
| Malformed, unknown, non-finite, or inconsistent contract field | Pydantic validation fails; CLI returns `2` | Caller fixes or migrates input |
| Missing, non-regular, or hash-mismatched referenced file | Integrity check fails before a report is emitted | Package/evidence producer restores the frozen file and digest |
| Expired policy/release, wrong population/game/interface, or incomplete provenance binding | Assessment aborts fail-closed | Policy/package/evidence authority recollects or corrects evidence; core never restamps it |
| Missing, screen-only, or weak evidence | Mandatory threat becomes `inconclusive` with `evidence_consistency=insufficient` unless a validated floor independently blocks | Assessor obtains admissible evidence or redesigns |
| Validated floor and ceiling contradict | Decision records `evidence_consistency=contradictory` and both producer evidence IDs; a floor over tolerance retains `block` and emits a structured integrity condition rather than becoming neutral | Independent assessor adjudicates producers; the blocking report remains unchanged |
| Analyzer routing ambiguity or returned capability/context violation | Assessment aborts without a report | Service operator fixes registry or worker contract |
| No feasible optimization candidate | `reject` only with certified exhaustive search; otherwise `redesign_required` | Configuration/optimization authority expands or corrects candidates |
| Invalid certificate, internally mismatched registry-head/sequence declaration, bad signature, broken event chain, or illegal lifecycle transition | Replay fails and creates no authorization; freshness against a live registry is outside the offline verifier | External authority regenerates a valid bound record and checks live state; production state is unchanged by MRA |
| MCP dependency, timeout, subprocess, or resource failure | Tool call fails; no lifecycle state changes | Local researcher/operator diagnoses or cancels outside MRA |
| Corrupt/interior-gap AuditStore record, predecessor, or SQLite sequence | `audit-verify` fails; valid tail deletion/replacement is detected only when expected ledger ID/count/head are supplied from an external checkpoint | Operator compares the immutable external checkpoint or restores and reconciles from protected records |
| Audited run fails or terminal append fails | A failure terminal is recorded when computation fails; completion must append before report output, and an orphaned intent fails complete verification | Caller investigates the bound run ID; there is no distributed transaction or retry manager |

## Repository and component map

| Path or logical group | Principal modules | Responsibility |
|---|---|---|
| Protocol and contracts | `docs/model-release-assurance-protocol.md`, `schemas/`, `formal/` | Normative lifecycle, public machine contracts, abstract semantics and proofs |
| Assessment core | `models`, `engine`, `decision`, `model_coverage`, `analyzers/*`, `services` | Strict contracts, source binding, local service routing, evidence semantics and fail-closed recommendations |
| Selection and certificates | `optimizer`, `decision_theory`, `portfolio`, `portfolio_statistics`, `incomplete_portfolio`, `protocol_feasibility`, `strategic_assurance` | Candidate selection, information ordering, simultaneous evidence, mathematical solving and replay |
| Protocol integrity | `release_protocol`, `integrity`, `audit`, `errors` | Lifecycle replay, hashes, Ed25519 manifests, local audit chain and error taxonomy |
| Evidence lab | `knowledge`, `mcp_tools`, `mcp_server`, `experimental_workflow`, `empirical_workflow`, `privacy_orchestration`, `red_team`, `scripts/`, `reproduction/` | Advisory retrieval, experimental workers, benchmarks and retained study designs |
| User and test assets | `examples/`, `tests/`, `docs/` | Executable examples, regression/replay coverage, normative/reference/guide documentation |
| Build and release | `pyproject.toml`, lock files, `Makefile`, `.github/` | Packaging, dependency tiers, verification gates and draft GitHub releases |
| Generated runtime data | ignored `output/` and experiment caches | Local reports, models, datasets, measurements, audit databases and benchmark output |

The package remains physically flat for compatibility; the table gives logical ownership without
changing import paths or hash-bound study records.

## Extension rules

1. Decide whether the change belongs to the supported core, experimental evidence lab, formal model,
   or external production system.
2. Add or version the Pydantic contract; export a new JSON Schema for public machine boundaries.
3. Define evidence direction (`exact`, `ceiling`, `floor`, or `screen`), coverage, realizability, and
   maximum decision capability. A floor never clears and a screen never decides.
4. Preserve release, policy, artifact, interface, population, decision-game, source, and time binding.
5. Add positive, malformed-input, substitution, expiry, replay, and capability-escalation tests. The
   evidence-direction matrix is mandatory: a floor must be tested never to clear under any input; a
   ceiling never to block; a screen never to decide; and exact evidence never to clear without
   complete coverage. Decision-bearing producers additionally need policy-version/digest rejection,
   context substitution, and contradictory-evidence tests.
6. Update examples, the schema map, architecture, project scope, security guidance, and changelog.
7. Preserve backward compatibility or publish a deliberate version migration; never silently restamp
   evidence or overwrite an older versioned schema.

For a remote analyzer, keep central decision authority in `AssuranceEngine`. The transport may return
typed evidence only; it must not authorize, mutate the portfolio registry, or expand its declared
scope. Production transport additionally requires workload identity, mTLS, attestation, replay
protection, request limits, deadlines, isolation, observability, and durable orchestration.
