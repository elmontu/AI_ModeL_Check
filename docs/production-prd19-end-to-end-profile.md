# PRD-19: one public profile end to end

Status: **in progress for production qualification**. The local implementation
connects one fresh bundled Wine sample through intake, a frozen combined plan,
native and SACRO-ML tests, independent review, atomic fixture activation, exact
delivery, expiry/revocation and historical receipt replay. This sector-neutral
framework targets agency private cloud; provider and region remain open.

## Combined plan and current evidence

The trusted bootstrap accepts only Wine, 128 rows and seed 20261001. It creates
a PRD-17 campaign and retains a separate immutable plan before fitting. The plan
binds its source/data/native recipe, recipient, implementation, pinned SACRO
runtime and fixed attack/control recipe. Target, positive and null cases use
all three frozen seeds. Old candidates and external benchmarks cannot attach.

PRD-13 registration and authenticated native replay remain unchanged. SACRO
tests the bytes from that same prospective fit. Independent numeric replay
checks retained input, splits, scores, controls and comparison. The descriptive
check takes the maximum symmetric membership AUC across three repetitions,
rounded upward to basis points, with a 9900 limit. This permissive fixture
criterion is not accepted agency scientific criteria, privacy or clearance.
Dependent repetitions, unestimated uncertainty and the non-DP model stay explicit.

A seven-stage journal records planned, native, external, assess, approve,
authorize and complete. Independent canonical people acknowledge the combined
native/external binding. Native-only approval cannot open this facade's route.
Comparison semantics are replayed before the external stage; each later guard
checks the exact six comparison-file hashes and binding. The original observer
also checks native artifacts, signed evidence, registration and all package
sources. Changed evidence is denied without repeating unchanged numeric work.

The fixture epoch starts at 1000 and advances with real monotonic elapsed time.
The original 120-second native evidence lifetime is never extended, restamped
or held still during external work. A slow run fails and retains partial output.
Evidence/activation deadlines use the final shared authority timestamp.
Activation and grant defaults retain the existing 30/20-second limits.

## Atomicity, lifecycle and custody

Authorization here is one atomic PRD-18 **public-fixture activation** commit.
The companion journal is a separate store. A crash between activation and its
journal acknowledgment can leave a historical activation unusable through this
facade. This is not a distributed transaction, real privacy charge or
PRD-15/16 production authority; existing commits are never rolled back.

The existing human-recipient grant and durable admission route delivers exact
candidate bytes. The rehearsal covers a complete transfer, a 128-byte partial
attempt reporting one byte, suspension/resumption, grant revocation, exclusive
expiry and permanent activation revocation. Unknown extents remain uncertain;
no observation proves recipient receipt.

Known journal/delivery pins detect prefix restores and forks. Final receipt/key
pins must be retained independently of the bundle by the trusted caller.
Same-host local storage is not independently administered agency custody.
Coherent rollback of all trusted floors, privileged Python/filesystem access
and machine-wide alternate egress remain outside this fixture boundary.

## Historical receipt replay

An ephemeral Ed25519 key signs the receipt in a separate purpose domain. Only
the public key is saved. Exact externally supplied receipt/key SHA-256 pins are
mandatory. Replay captures bounded ordinary files, rejects extra/missing or
linked artifacts, replays captured SQLite histories without modifying files,
and checks source/data/plan, native numeric results and archival RSA signature,
external comparison, independent records, activated bytes, all admissions and
observations, checkpoints and terminal lifecycle.

The new fixture retains the native signer's public registration. Replay never
constructs a backdated current trust registry. Matching code/runtime is needed
for deterministic numeric replay. Success is historical_fixture_replay_verified;
current authorization, original-training/external-execution attestation, agency
trust and recipient receipt remain false. Negative probes are trusted local
observations, not reconstructed execution. Historical approval grants no live
permission after restart.

## Run and replay on D

From the government checkout on D, use the existing pinned SACRO interpreter:

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .venv-pipeline/Scripts/python.exe -B scripts/rehearse_public_profile.py --profile local_public_fixture --python .local/verification/prd14-sacro-20261001/sacro-env/Scripts/python.exe --output .local/public-profile-v1
~~~

Choose a new ignored output directory. Default production is refused before
output/training. Private data, model paths, alternate recipes, caller admissions
and old comparison attachments are absent. The existing runtime is not modified.

Retain the returned receipt/key pins outside the run bundle, then replay:

~~~powershell
& .venv-pipeline/Scripts/python.exe -B scripts/rehearse_public_profile.py --profile local_public_fixture --replay .local/public-profile-v1/run --expected-receipt-sha256 RECEIPT_SHA256 --expected-key-sha256 KEY_SHA256
~~~

Replay creates no output or current authorization. A live run needs fresh
execution and independent review. Runtime selection verifies the separate
73-dependency lock/metadata; the worker checks pinned package/runtime bindings.
Installed-wheel verification uses a new compatible environment so parent
dependencies cannot shadow the external runtime.

Portable required tests use explicit fictional child probabilities alongside
real native fitting, crypto and stores. They do not demonstrate SACRO execution.
The separate Windows rehearsal runs the actual worker and retains all nine
case/repetition outcomes. Final tests/builds/preservation are recorded at
.local/verification/prd19-profile-20261002/validation.json.

## Remaining production acceptance

Scientific criteria/accounting, qualified private intake, agency IdP/KMS,
independent signed custody/witnesses, atomic real-model authorization/charge,
PostgreSQL/cloud failover, protected alternate egress, TLS/network streaming
and scale acceptance remain pending. No Linux/cloud or agency release is claimed.
Earlier implementation and evidence remain preserved on D; the retired archive
remains retired. GitHub publication still needs authentication.

Next is **PRD-20**, monitoring, audit custody, alerts and incident runbooks.
