# PRD-03: local source and build baseline

**Record:** PRD-03 / revision 0.1 / 1 October 2026.
**State:** `in_progress` — local baseline work; publication and protected
release configuration remain pending.
**Parent:** [production roadmap](production-private-cloud-plan.md).
**Scope:** government repository on D:,
base commit `0b9958954f30134e9662d0797bd465df26051806` plus the current working
tree. The original research and separate academic repositories are outside this
task.

## Baseline identity and preservation

The commit alone does not contain the current red-team implementation, archive
retirement or production records. A reviewed local baseline must include
modified tracked files and new, nonignored source/tests/docs, and explicitly
record tracked deletions. Keep the 28 September archive deleted in the current
checkout; its recovery point remains in Git history.

The [baseline utility](../scripts/verify_build_baseline.py) captures the present
source inventory, exact byte hashes, deleted tracked paths, Git status, HEAD and
staged-entry identity without staging, committing or changing branches. It
copies source bytes to a fresh ignored output directory and checks for source
changes during capture and after the build. Preserve existing source line
endings: historical manifests can bind raw bytes.

The utility excludes Git internals and ignored environments, caches, local
stores, generated outputs and prior baseline runs through the Git inventory.
It rejects symlink/reparse or escaping input paths and refuses to overwrite an
existing output. This inventory is a trusted local developer tool; it is not
a secret scanner, signed source attestation or defense against a privileged
administrator changing the repository and its receipts together.

Review of the current changes covers these areas:

| Area | Review result and limit |
| --- | --- |
| Archive cleanup and navigation | Preserve the requested archive deletions and current advisory/navigation edits; historical verification stays labelled historical |
| Operational red-team screen | Keep strict bindings, controls, freshness and non-authorizing results; current profile remains the public GaussianNB fixture and separately configured temporal policy |
| Discovery | Include the new discovery module and tests in the wheel baseline; external frameworks remain explicitly unintegrated and source-only tools cannot appear installed |
| Temporal screening | Preserve report invalidation and repeated eligibility checks; trusted local storage/administrator assumptions remain |
| Production records | Include PRD-01/02 proposals without converting missing agency decisions or deferred provider/region choices into approvals |
| Build tooling | Add exact local builder pins, immutable run inputs, repeat builds, package-byte checks and explicit failure receipts |

This is a bounded engineering review plus regression/build evidence, not an
independent production security or scientific assessment.

## Build inputs and repeatability

[requirements-build.lock](../requirements-build.lock) pins the tools used for
this local build profile: pip 25.0.1, setuptools 84.0.0, wheel 0.48.0 and packaging
26.3. The observed interpreter is Windows x64 Python 3.12.14. These pins capture
the chosen local toolchain; they do not claim that those versions are the
latest, approved for production or installed on every supported platform.

The utility verifies the installed build-tool versions before building. It uses
`pip wheel --no-index --no-deps --no-build-isolation --no-cache-dir` against
two separate copies of the captured source with a fixed `SOURCE_DATE_EPOCH`
from the base commit. Each build has separate output and temporary directories.
The builder clears PYTHONPATH and user-site configuration but reuses the current
virtual environment, including its editable .pth hooks. Exact package-member
comparisons detect different packaged source bytes; they do not make the build
hermetic. The runtime receipt records search paths and .pth identities alongside
tool versions. A fresh approved builder without checkout hooks remains later
production packaging work. Logs are retained with the manifest.

Acceptance requires equal wheel SHA-256 values, expected package contents and
valid wheel RECORD hashes. Every selected package source/static file must match
its input bytes; missing, extra or changed package members fail the check.
Package version remains `0.8.0`; use the source-manifest and wheel hashes to
identify this working-tree baseline, not the version string alone.

Two matching builds demonstrate repeatability for this captured source and
local toolchain. They do not establish cross-platform reproducibility, a
reproducible source distribution, a fresh dependency resolution, dependency
artifact authenticity or a reproducible production image.

| Input | Current boundary | Later work |
| --- | --- | --- |
| Core `requirements.lock` | Exact versions, without artifact hashes | PRD-09 approved dependency artifacts and complete production lock |
| Console/experiment requirements | Compatibility ranges; exact installed versions captured in each receipt | PRD-04 explicit test runtime; PRD-09 supported production/adapter locks |
| `pyproject.toml` | Broad build-backend requirement remains compatible with source installation | This local verification uses the separate exact builder lock |
| Development Dockerfile | Mutable base tag, OS package install, dependency ranges and editable install | PRD-09 immutable image/build inputs, provenance and deployment admission |
| Local build receipt | Unsigned source/tool/output identities and observed checks | Protected release identity and independently retained attestations before production publication |

## Run and inspect

From the government repository root, using the existing matching builder:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B scripts/verify_build_baseline.py --output .local/build-baseline/prd03-20261001
```

Use a new output directory for every attempt. The utility performs no package
installation and retains failed outputs for diagnosis. Provision a matching
builder separately from approved artifacts if the version check fails; do not
weaken the lock to make a receipt pass.

The run directory holds the source manifest/snapshot, independent build logs and
wheels, runtime details and result receipt. Local test and installed-wheel smoke
evidence are retained separately under
`.local/verification/prd03-source-build-20261001/`. Both locations stay on D:
and are ignored by Git. A local source snapshot may include retained public
documentation/reproduction inputs; it is not a publication allowlist.

The existing government regression suite ran 1,025 tests: **1,007 passed,
18 skipped, zero failures/errors**. Skips concern optional PyTorch/privacy
dependencies and Windows symlink capability. The new baseline utility's focused
tests and final build/smoke results are recorded separately in the validation
receipt; this count does not silently include tests added after discovery.

For a complete local acceptance record:

1. Run the full government suite with the console and experiment dependencies;
   record optional/platform skips. Run the schema, documentation-link and
   relevant JavaScript syntax checks.
2. Run the baseline utility against the final files, retaining failure as well
   as success evidence. Do not edit source after capture and continue calling it
   the same baseline.
3. Install the resulting wheel into a separate package target. Run with isolated
   Python startup, no checkout `PYTHONPATH` or editable-install hooks, and
   assert that application imports resolve to that target. Record any reuse of
   the existing dependency environment rather than call it a clean reinstall.
4. Check CLI version/example/schema operations, packaged UI assets and
   discovery. Run the installed public red-team fixture, evaluate its exact
   candidate, and verify that altered bytes fail. These are public-data software
   smoke tests, not private-model validation.
5. Bind the test logs, wheel smoke results and baseline manifest/wheel hashes
   in the final local validation receipt.

## Publication and PRD-04 handoff

PRD-03 remains in progress until its publication and governance gates are
satisfied. GitHub authentication is pending; this task does not push, publish,
tag, merge or change repository settings. The existing
[release process](releasing.md) also requires a public-use licence/disclosure
decision, appointed release owner/reviewers, security reporting, release
version/changelog, complete verification and protected attestation. The local
wheel is a development artifact, not a release candidate approved by an agency.

Once authentication and ownership decisions are available, inspect the actual
repository settings and configure branch protection around the agreed reviews
and required checks. Verify the remote source commit, protected branch, run
results and published artifact hashes; do not infer protection from a YAML file.

PRD-04 can now use the captured local inputs to implement its CI changes while
publication remains a separate gate. Its concrete gaps include:

- Explicitly run export-red-team and discovery tests plus all temporal suites
  with API dependencies. The existing API-enabled patterns omit
  `test_temporal_red_team.py`; general discovery can skip its API tests without
  FastAPI/httpx.
- Require API-enabled workflow results before accepting the package job. Its
  current dependency list omits `pipeline-bootstrap`.
- Give release verification the required console/API dependencies and fail on
  skips of required supported-profile tests.
- Preserve separate optional experiment/platform coverage and recorded skips;
  formal proof, source-distribution/twine validation, remote CI and protected
  release signing remain distinct checks.

No PRD-01/02 agency approval, provider/region choice or deployment permission is
created by this source/build milestone.