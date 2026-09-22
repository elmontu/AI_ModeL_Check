# Government-only publication verification

This record covers the government implementation and documentation selected for
GitHub on 22 September 2026. The revised academic manuscript, its draft archives,
ACS study runners and new study outputs were excluded. Previously published
academic artifacts remain at their existing Git revision.

Validation used a clean export of the Git staging area. Dependencies came from
the existing local Python runtime, while Python imports were checked to resolve
to the exported source tree. Unstaged research files could not satisfy missing
publication dependencies. The link-checker change was tested separately after
the main suite; its five new tests are additional to the 958-test run.

| Check | Result | Retained evidence |
| --- | --- | --- |
| Main suite | 958 run; 957 passed; one Windows symlink capability skip; zero failures/errors | [Main log](main-tests.log) |
| Existing published academic baseline | 43 run and passed; zero skips | [Baseline log](academic-baseline.log) |
| New Markdown checker regressions | Five run and passed | [Regression log](link-tests.log) |
| Published documentation links | Passed; twelve links into ignored `output/` reported as local-only generated artifacts, not checked | [Link check](links.log) |
| Schema replay | 37 current schemas match their unchanged manifest | [Schema check](schemas.log) |
| Browser scripts | Syntax checks pass for console, export lab and temporal service | [JavaScript check](javascript.log) |
| Distribution | Wheel builds; isolated installation imports from the installed wheel, contains all nine web assets and four entry points, and runs the export catalog | [Build log](wheel-build.log), [install checks](wheel-smoke.json), [catalog](wheel-catalog.json) |

The [verification receipt](verification.json) records runtime versions, exact
source/test/schema hashes, the wheel hash and retained-log hashes. The wheel and
temporary export are local build products, not committed artifacts. Log bytes
are preserved from capture. This index and the receipt itself are excluded from
the retained-log hash map to avoid self-referential hashes.

Reproduce from a fresh checkout with the appropriate optional test dependencies:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m unittest discover -s tests -v
python -m unittest discover -s academic/tests -v
python scripts/generate_schema_manifest.py --check
python scripts/check_markdown_links.py
node --check src/model_release_assurance/console/static/app.js
node --check src/model_release_assurance/export_poc/static/app.js
node --check src/model_release_assurance/temporal_assurance/static/app.js
python -m pip wheel --no-cache-dir --no-deps --no-build-isolation --wheel-dir output/wheels .
```

The final test inventory includes the five checker regressions, so a subsequent
complete main-suite run will discover 963 tests. Optional dependency and platform
availability can change skip counts; the receipt gives this run's actual runtime.
The normal console setup does not install every optional research dependency.

The earlier [local integration results](../government-audit-update-20260922/README.md)
remain historical workspace evidence with their original source/runtime bindings.
Their larger counts include separate academic work and are not the count for this
publication. The [government integration report](../../docs/government-audit-update-2026-09-22.md)
describes functionality and boundaries. These checks do not establish exhaustive
adversary coverage, general model privacy or agency release authorization. This
publication check did not execute Docker, rebuild Lean or re-run the historical
training/adversary matrix. GitHub CI results are reported separately after push.
