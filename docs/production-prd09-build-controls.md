# PRD-09: dependency artifacts and local build evidence

Status: **in progress**. The local public-fixture implementation is available;
production qualification and agency approval remain pending. Work stays in the
D: government checkout. Provider and region
remain open. No private agency data, deployment, GitHub publication or
production signing key is involved.

## Locked scope

The checked-in [Windows manifest](../deploy/build/windows-cp312.json) and
[Linux manifest](../deploy/build/linux-cp312.json) describe 31 exact wheels each
for CPython 3.12.14, Windows x64 and Linux x64 with manylinux 2.28 compatibility.
They cover the core package dependencies, API console, scikit-learn 1.6.1
tabular adapter and four local builder tools. Every wheel has a filename,
version, size and SHA-256. The accompanying
[Windows](../deploy/build/windows-cp312.requirements.txt) and
[Linux](../deploy/build/linux-cp312.requirements.txt) requirements contain the
complete transitive closure with hashes.

The verifier checks root requirements and extras against the explicit target
environment, then traverses requirements from the actual wheels. Missing,
incompatible, unreachable or direct-URL dependencies fail. Unsupported target
markers fail instead of borrowing host settings. Wheel tags, Python version,
distribution identity and bounded ZIP metadata must agree with the lock.
Unsafe paths, aliases, links, duplicate members, encrypted entries and oversized
metadata are refused. Wheels are inspected without extracting or importing code.

This profile does not cover pandas, Arrow, XGBoost, deep-learning/LLM/vision
adapters, MCP, every research option or operating-system packages. Each supported
production adapter still needs its own reviewed lock and target execution.
The older convenience bootstrap and development Dockerfile retain their broader
dependencies; neither becomes a qualified production image through this work.

[Hash checking and binary-only installation](https://pip.pypa.io/en/stable/topics/secure-installs/)
bind selected bytes and avoid source-build resolution. They do not authenticate
a publisher, prove safe code or establish provenance of native libraries
embedded inside wheels. The new `build-controls` package extra supplies the
optional metadata parser; the checked-in verifier bootstrap pins its wheel hash.

## Inventory, licenses and advisories

`production_build.artifacts` emits a dependency graph and a
[CycloneDX 1.6](https://cyclonedx.org/schema/bom-1.6.schema.json) dependency SBOM,
with package URLs, wheel hashes and declared license evidence. License-file
hashes and absent declarations are recorded. This is an inventory of selected
Python distribution artifacts, not a whole-container or application SBOM;
vendored native code and OS components require additional inventory.

License declarations are untrusted package metadata, not legal approval.
The [local policy](../deploy/build/policy.json) keeps `license_review=pending`.
This repository also lacks an approved project license. No license allowlist,
legal decision or production approval is invented.

The CLI queries the [PyPI version JSON API](https://docs.pypi.org/api/json/)
for every exact locked name/version, including builder tools. Only public
package identifiers are sent. Fetches are bounded and limited to PyPI metadata
and the exact locked files on its file host; errors never become clean scans.
Raw response bodies and hashes are retained in observations. The evaluator
reparses these bodies, rejects missing/extra/duplicate observations and requires
complete coverage with no reported advisories. Observations from the future
or older than 24 hours fail. A live scan requires successful fetches. Offline
evidence evaluation checks supplied observations and their age; it does not
test current network availability.

This is a known-vulnerability metadata check, not pip-audit execution, exploit
reachability analysis, malware scanning, SAST, license approval or container
scanning. A trusted local fetcher supplies observation time and origin;
unsigned saved responses are not independently authenticated evidence.

The first check on 1 October 2026 found published advisories in
`cryptography 49.0.0` and `pip 25.0.1`. The lock and local verification runtime
were updated to `cryptography 50.0.0` and `pip 26.2.1`. Initial vulnerable
locks, response bodies and affected wheels remain in ignored local evidence.
The cryptography update addresses the upstream
[PKCS#7 decryption advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5);
discovery in a dependency does not establish that this application invokes the
affected path. Existing PRD receipts remain historical and unchanged.

## Local provenance and admission

`production_build.evidence` signs a bounded, domain-separated local statement
with an ephemeral Ed25519 key. It binds the built wheel, source manifest,
dependency manifest, inventory, SBOM, policy, advisory report, required-test
receipt, build result and exact builder versions. The build-signing domain is
separate from PRD-08 access-token keys.

The verifier requires a caller-supplied pinned public key, expected context,
current time and active-signer decision. It rejects tampering, changed context,
expired statements, inactive signers and malformed fields. Admission takes one
owned snapshot of mutable inputs, recomputes actual evidence hashes and current
advisory eligibility, checks builder inventory and requires a passed government
profile with nonempty coverage and zero skips. All Python test/helper source hashes must match
the actual build source manifest, including helper modules outside test selection. The two build subjects must match the signed
wheel and the build must finish with stable source.

`verify_build_provenance.py` also checks the current checkout and actual wheel
bytes against the supplied baseline before issuing its local fixture statement.
It saves a public pin and expected context alongside the statement for replay;
these files are illustrative outputs, not an independent trust root. The
private key remains only in process memory. A trusted caller must supply policy,
expected context, signer status and evidence; a valid signature cannot prove
the truth of a malicious builder's claims.

All reports keep production authorization and deployment false, even when all
fixture checks pass. With the checked-in policy, cryptographic verification
can pass while admission reports `license_review_pending`. Exit zero from the
fixture CLI may report that expected blocked state; inspect its explicit fields.
This custom envelope claims no [SLSA level](https://slsa.dev/spec/v1.1/provenance),
hermetic build, protected signing service or agency attestation.

## Replay and retained evidence

Run from the D: government repository using a prepared Python environment with
the core dependencies and hash-pinned verifier parser. Choose fresh output
directories; existing evidence is never overwritten.

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_supply_chain.py --manifest deploy/build/windows-cp312.json --download --scan-pypi --output .local/supply-chain-windows
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_supply_chain.py --manifest deploy/build/linux-cp312.json --download --scan-pypi --output .local/supply-chain-linux
& .\.venv-pipeline\Scripts\python.exe -B scripts/run_required_tests.py --profile government --output .local/required-prd09
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_baseline.py --output .local/build-baseline/prd09
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_provenance.py --build-baseline .local/build-baseline/prd09 --test-receipt .local/required-prd09/result.json --supply-chain .local/supply-chain-windows --manifest deploy/build/windows-cp312.json --policy deploy/build/policy.json --output .local/provenance-prd09
```

For an already downloaded exact wheelhouse, replace `--download` with
`--wheelhouse <directory>`. Omit `--scan-pypi` only for an explicitly incomplete
offline artifact check; it returns nonzero and cannot be called a clean scan.
Neither command installs wheels. A separate clean environment can install with
`--no-index --find-links <wheelhouse> --only-binary=:all: --require-hashes -r
deploy/build/windows-cp312.requirements.txt`. Do not install Linux wheels into
Windows.

The government required profile includes all four new build-control suites and
hashes every Python test/helper, both manifests, both installation locks,
the verifier bootstrap lock and policy. Missing files or changes during a run fail. CI and release prerequisite
jobs on Windows/Ubuntu now retain public artifact/advisory evidence and fail on
incomplete scans. Those jobs still test through the older broader bootstrap;
they are not locked-runtime qualification. Remote execution remains pending
GitHub authentication. CI action/image pins and protected release configuration
remain open.

Local verification receipts are under
`.local/verification/prd09-build-controls-20261001/`; the repeat-build baseline
is under `.local/build-baseline/prd09-20261001-final/`. The Windows profile was
installed offline into a fresh environment, and pip found no dependency
conflicts. The full government suite uses the existing broader test environment,
which includes older XGBoost/Arrow test requirements outside this narrow lock.
Targeted build, identity, storage and trust tests exercise the smaller locked
environment separately; this is not whole-framework locked qualification. Linux wheel metadata and dependency closure were checked on Windows;
Linux runtime acceptance requires a Linux runner.

## Observed local results

On 1 October 2026, **601 required government tests passed with zero skips,
failures or errors**. This includes 72 new tests: 15 artifact, 29 evidence,
15 supply-chain CLI and 13 provenance CLI checks. The fresh locked Windows
environment separately passed **243 targeted identity/storage/trust/build
tests with zero skips**. These overlap the full required suite; they are not
additional unique coverage.

Another 35 runner/documentation tests passed. The unchanged build-baseline
suite also passed 15 tests, with one Windows symlink-creation test unavailable;
the new build-control suites exercise hardlink and reparse refusal separately.
Both dependency scans covered all 31 locked distributions and reported no
advisories after the two pin updates. CI YAML structure and fail-on-error gates,
57 Markdown link inventories and whitespace checks passed locally.

The existing 97 package files from PRD-08 remain unchanged. Earlier milestone
evidence and the 123 deliberate archive deletions remain preserved. The final
local validation receipt records exact-source test hashes, wheel results and
fixture admission separately from pending production controls.

## Production closure

PRD-09 still requires agency review of dependency and project licensing,
adapter support and advisory response policy; a controlled dependency mirror;
reviewed OS/container inputs pinned by digest; native-component, code and
container scans; isolated builders and signed release provenance; independent
trust and revocation custody; and a deployed admission service that rejects
unapproved images and evidence. Qualify both target environments, the actual
cloud runtime and all production adapters before admitting private data.

The next local milestone is documented in [PRD-10](production-prd10-durable-jobs.md):
durable job state, leases, scoped grants and controlled public-fixture workers.
The public-fixture groundwork does not remove the agency decisions or deployed
acceptance work from earlier tasks.
