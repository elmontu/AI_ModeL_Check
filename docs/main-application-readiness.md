# Readiness and learning in the main MRA application

The local MRA application includes readiness, evidence and learning pages at
`/assurance/`, alongside the dataset and model workflows at the application
root. The `mra-console` entry point composes these routes in one application.
A separate readiness server is unnecessary for native navigation.

A fresh source or wheel installation opens a clearly labelled **fictional demo**.
Its decisions and source assumptions teach how requirements relate to one
another. They supply no authentic evidence, agency appointment, approval or
release authority. Real agency decisions remain pending. Project captures require
an explicit private configuration and keep their own integrity checks.

## Start a review session without a worker

This update is published on `codex/mra-platform-codebase` pending a separate
merge into `main`. Obtain the matching source before installing:

```console
git clone --branch codex/mra-platform-codebase https://github.com/elmontu/AI_ModeL_Check.git
cd AI_ModeL_Check
```

For an existing checkout, fetch the published branch and select
`git checkout codex/mra-platform-codebase`. A wheel should be built from that
same reviewed source revision.

Use Python 3.11 or newer and a new environment:

```console
python -m venv .venv
```

Activate `.venv\Scripts\Activate.ps1` in Windows PowerShell or run
`source .venv/bin/activate` on Linux/macOS. From a source checkout, install:

```console
python -m pip install ".[console]"
mra-console serve --data .local/console-data --host 127.0.0.1 --port 8765
```

Open [the main application](http://127.0.0.1:8765/) and use **Readiness & learning**.
The serve process creates its ordinary local application store where needed;
it starts no worker, training job or benchmark. Keep the service on loopback for
this local review workflow. Stop it with Ctrl+C.

For a wheel installation, replace the install command with
`python -m pip install "./dist/<built-wheel-name>.whl[console]"`, substituting the
exact wheel filename. Run the same serve command from an ordinary working
directory. The wheel includes the application modules, static assets and
fictional lesson rules. Project captures and historical results remain external.
The minimal console extra does not install every optional training or research
runtime; unavailable research prerequisites remain explicit.

The full `scripts/start_demo.py` and `mra-console local` launchers retain their
separate API-plus-worker behavior. Starting one is an operator choice. Their
existence does not mean a review-only session has started a worker.

## Find the tools

The main **Readiness & learning** panel provides these entries. The panel remains
visible on small screens where the original sidebar is hidden.

| Entry | What it explains or preserves |
| --- | --- |
| Readiness overview | The selected fictional preparation state, or an explicitly configured captured view with its limits. |
| Gap checklists | The obligations affected by a decision or source assumption; a fictional satisfied item is not a real gap closure. |
| Evidence register | The selected evidence descriptions and their limits. Demo assumptions are labelled as fictional. |
| Tutorial examples and Interactive tutorial | Fixed examples and editable choices showing why different assumptions change requirements. |
| Compare demos | Two configurations side by side, including the checklist items and reasons that differ. |
| Guided tutorial | A sequence for comparing configurations and interpreting the differences. |
| Guided practice | Exercises in which applied choices produce explanations of checklist changes. |
| Saved demos | Named fictional configurations saved in the current browser, with exact practice and comparison links. |

Captured-mode navigation also retains intake, field-guide, review-handoff,
preserved-findings and local-status routes. A return link leads back to the main
MRA application. A missing captured prerequisite is shown as unavailable; it is
never substituted with an authentic-looking demo record.

## Apply, save, reload and compare practice choices

Choose a practice exercise, change a decision or source assumption, and select
**Explain my changes**. Review the explanation before selecting
**Save this practice configuration**: the save link represents the last applied
choices. Give the saved demo a useful name so it can be distinguished later.

Open **Saved demos** to reload a practice configuration or choose two entries for
comparison. Reloading recomputes explanations using the installed finite lesson
rules. It does not preserve a scientific result, editing history or learning
grade. A later application version may explain the same assumptions differently;
the saved configuration remains a record of the selected choices.

Browser storage belongs to an origin, which includes the protocol, host and
port. Another port, browser profile or computer has a separate library. Export a
backup before clearing browser data or moving to a different local installation.
Saved demos contain fictional choices and should not be used to store confidential
agency decisions or source material.

Saved-demo exports retain the earlier fictional-format compatibility fields,
including its fixed open/closed-count guards. These are format metadata used to
accept the same demo files across versions. They make no claim about actual
project status, authentic evidence or agency approval.

## Move an existing saved-demo library

An older readiness workspace and the native application can use different
origins. For example, a library at port 8770 is separate from the native
`http://127.0.0.1:8765/assurance/practice-saves` library.

1. Open the older workspace's **Saved demos** and select **Export saved demos**.
2. Keep the JSON file in its exported format.
3. Open the native **Saved demos**, choose the file and select **Import demo file**.
4. Check the imported entries and reopen one practice or comparison link.

Imports create new copies and preserve existing saves at both origins. Repeated
imports may create repeated names; each list item identifies its exercise and
position. The browser does not upload this demo file to an agency evidence store.
There is no automatic cross-origin copy or storage reset. If an older service
is stopped, its library remains in that browser profile; reopening the same
origin makes it accessible again.

## Inspect private captured inputs explicitly

Keep project profiles and evidence outside published source and wheel files,
for example in an ignored `.local/` directory. Select a profile with the
`--readiness-config PATH` CLI option or the `MRA_READINESS_CONFIG` environment
variable. The CLI option identifies the intended profile directly. A profile
uses schema `mra-readiness-captured-config/1` and binds these fields:

| Field | Meaning |
| --- | --- |
| `schema` | Exactly `mra-readiness-captured-config/1`. |
| `bundle`, `manifest_sha256` | Captured readiness directory and its actual recorded manifest digest. Both are required. |
| `intake_report`, `intake_manifest_sha256` | Optional intake directory and its matching recorded manifest digest, supplied together. |
| `handoff_packet`, `handoff_archive_sha256`, `handoff_manifest_sha256` | Optional review-packet directory, archive digest and manifest digest, supplied together with the intake configuration. |
| `suspend_presentation` | Optional boolean selecting presentation suspension at startup. |

Paths are resolved relative to the profile file. Obtain pins from the existing
captured completion and manifest records; do not invent replacement hashes or
copy demonstration placeholders into a real profile. The loader checks the
profile shape and the captured readers validate the actual inputs. A selected
invalid or missing profile must fail explicitly rather than fall back to the
fictional demo.

For example, after preparing a valid private profile:

```console
mra-console serve --data .local/console-data --host 127.0.0.1 --port 8765 --readiness-config .local/readiness-profile.json
```

Captured pages recheck their configured inputs on every request, including
requests that are refused. Missing or changed inputs withhold captured readiness
content and retain a local-status route; they do not turn an unsupported finding
into a pass. Original JSON and archive downloads retain their captured bytes.
The main application's other pages remain separate from that captured view.

## Keep evidence and decision authority separate

The main application may display saved model cases, earlier results and learning
pages together. They remain different records. A fictional choice does not
update a model case, authentic source evidence, an agency response, an appointment
or a release decision. Agency-owned requirements stay pending until the
responsible authority supplies and accepts the required evidence.

Captured-mode gap counts describe their selected evidence snapshot. Demo counts
describe fictional teaching configurations. Neither is a substitute for a current
agency decision. Earlier adverse, incomplete and unsupported findings must remain
preserved in their original project records.

The general advisory DOCX remains a separate, general and maths-free book. Keep
project-specific source pins, actual findings, qualification observations and
integration evidence in separate project files. Publishing application code does
not publish those files or make local verification agency acceptance.

## Request and qualification boundaries

Readiness presentation uses GET/HEAD routes, strict query values and scoped
content-security policies. The captured adapter keeps the readiness policies
separate from the main console middleware. ASGI limits concern server-provided
raw targets and header records; they do not claim to reproduce physical HTTP
wire-line parsing inside the separate standard-library server.

The automatic readiness workflow covers bounded finite application behavior and
clean-wheel packaging without a worker, project evidence or benchmark execution.
Tests and browser observations support only the flows and environments actually
checked. They do not establish production readiness, universal accessibility,
scientific validity, authentic source completeness or agency acceptance. The
existing full CI retains its triggers and broader workload coverage. Review the
selected workflow and its commands before starting scientific, training or
deployment checks.
