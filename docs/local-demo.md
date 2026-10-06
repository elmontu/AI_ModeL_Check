# GitHub demo on your computer

This walkthrough trains a small public-data model, exports it, inspects red-team
findings and records an educational government audit. Clone the GitHub repository
and start its local web console with one command.

Use the bundled or configured public research data only. This walkthrough uses
public data and does not qualify private agency data, authorize model release or
qualify a production deployment. No public-use
licence has been selected; repository visibility and this walkthrough do not
grant general permission to reuse or redistribute the software. See
[the repository licensing notice](../README.md#support-and-licensing).

## Clone and start

Use Python 3.11 or newer and Git. Choose a directory outside OneDrive or another
synchronized cloud-storage folder if you want evidence to stay on your computer:

```console
git clone https://github.com/elmontu/AI_ModeL_Check.git
cd AI_ModeL_Check
```

From the checkout, run one command:

**Windows PowerShell**

```powershell
python scripts/start_demo.py
```

**Linux/macOS**

```bash
python3 scripts/start_demo.py
```

On first use, the launcher runs the existing setup script with the console
profile to create `.local/demo-venv`. Subsequent launches validate and reuse the
launcher-managed environment rather than reinstall it. An unrelated or incomplete
environment is not silently reused. First installation requires package access
or a prepared wheel directory; the bundled public datasets need no subsequent
dataset download.

The launcher starts a local web service and a separate worker. Open
[the console](http://127.0.0.1:8765/). The services share a SQLite queue and case
artifacts under `.local/demo-data`. Local mode binds to loopback for trusted
testers on one computer; it is not a shared public service.

The [README flow diagram](../README.md#run-the-github-demo-locally) shows the
steps from checkout through evidence download. Manual installation is also
available in [Quick start](../README.md#quick-start).

## Follow the public-data flow

1. Under **Train → export → assess**, select **Open training wizard**. Name the
   case `Public Wine demo` and select **Wine classification**. This bundled
   dataset has 178 samples, 13 features and three classes.
2. Select **Next**. Choose **Logistic regression** under **Model family**. Select
   **Next**, inspect the summary and select **Start training**. Compatible tools
   run automatically after training and export; unsupported tools remain visible.
3. Inspect the run details and **Red-team coverage**. Expand each tool to read its
   measurements, budgets, baselines and assumptions. Read the scientific result
   separately from the execution state. In the Wine/logistic example, ten checks
   finish and tree-leaf exposure is unsupported, so overall red-team coverage
   remains incomplete. A completed run can be blocked or inconclusive; a completed
   attack does not establish safety.
4. Select **Open trained model case**. The generated case uses **Education** mode
   and binds the candidate, lineage, request, evaluation plan and utility report.
   Select **Check inputs** to inspect required bindings and optional institutional
   gaps. **Run assessment** can repeat the assessment on the current bindings.
5. Open **Government audit review**. Review the twelve controls, choose **Evidence
   recorded**, **Gap identified** or **Not applicable**, and save your rationale.
   Evidence-recorded entries require a current bound file; selecting one verifies
   its bytes, not whether its contents answer the question. Identify agency scope,
   security and independent-review gaps honestly. See the
   [government audit guide](government-audit-guide.md) for the controls.
6. From the run details, use **Download evidence ZIP** and **Download result
   JSON**. From the review, use **Download review JSON**. Retain them together:
   the ZIP contains run artifacts, while the review JSON contains the separate
   checklist and outstanding gaps. Download partial evidence for failed attempts
   as well. Changed bindings or cited bytes make affected review entries stale.

Use **Run scenarios** to explore the eight fictional reference cases. Use
**View support and gaps** to inspect supported model families and missing
integrations before trying other presets. Four bundled datasets and ten CPU
presets are listed, alongside four optional configured research profiles; only
compatible combinations can run.

Training/export evidence is scoped to the generated public fixture. The console
does not automatically register it in the separate temporal release broker.
That dashboard and its retained research inputs are separate workflows.

## Use existing public research data on D:

The default launcher needs no external dataset directory. To enable the four
already prepared public research profiles on this computer, stop the console and
restart it with an explicit data root:

```powershell
python scripts/start_demo.py --research-data-root D:/model_audit_data
```

On Linux/macOS use `python3` and the existing absolute local source root. This
option configures read-only research inputs; `.local/demo-data` still stores new
cases and results separately. To restart the same configured session, repeat the
option. It does not relocate, overwrite or download source data.

In **Open training wizard**, the research choices become enabled when the root is
configured. Choose a dataset below, select **Next**, and start with **Logistic
regression** or **Random forest**. Regression and the digits-only CNN preset do
not apply to these binary classification profiles.

| Sample public dataset label | Dataset ID | Public covariates | Historical utility target |
| --- | --- | ---: | --- |
| ACS census and income (local research) | `research-acs` | 8 | Income classification |
| BTS aviation (local research) | `research-bts` | 7 | Departure disruption |
| HMDA mortgage lending (local research) | `research-hmda` | 7 | Loan origination |
| NYC TLC taxi mobility (local research) | `research-tlc` | 4 | Trip duration over 30 minutes |

Each fixed source directory is:

```text
D:/model_audit_data/experiments/mixed-model-export-20260929-v1/<corpus>/data/
```

Replace `<corpus>` with `acs`, `bts`, `hmda` or `tlc`. The loader expects the existing
`data.npz` and `manifest.json`; this is not an arbitrary CSV/NPZ upload interface.
It checks the retained manifest and source bytes, uses the public covariates `B`
and utility labels `y`, and omits withheld attributes `z`, record keys and other
research metadata from the returned training matrix.

Three sizes have different meanings: the much larger raw public-source collection,
the retained **27,000-row prepared matrix** for each profile, and the fixed-seed
sample of at most **4,096 rows** used by this console run. Enabling these choices
does not train on the entire raw collection. Historical training data is reused;
person-level disjointness, fresh audit status and independent qualification are
not established. The [PRD-11 source record](production-prd11-adapter-benchmarks.md)
documents the existing prepared data and its limitations.

Configuration enables selection; it does not prove every source is present or
valid. A missing, changed or rejected source fails the run and retains the error.
There is no automatic dataset download or fallback to a bundled dataset. Without
a configured research root, research choices stay disabled while the original
four bundled datasets continue to work. The console also accepts the trusted
local `MRA_DEMO_RESEARCH_DATA_ROOT` environment variable; the launcher option
above is the explicit way to configure this session. Inspect actual utility, red-team outcomes and
unsupported coverage rather than expecting a successful or safe result.

## Launcher options and retained evidence

Use `python scripts/start_demo.py --help` to see the available options. On
Linux/macOS, use `python3` instead. For example:

```console
python scripts/start_demo.py --install-only
python scripts/start_demo.py --port 8766
python scripts/start_demo.py --data PATH_TO_LOCAL_EVIDENCE
python scripts/start_demo.py --venv PATH_TO_NEW_DEMO_ENVIRONMENT
python scripts/start_demo.py --wheelhouse PATH_TO_PREPARED_WHEELS
python scripts/start_demo.py --research-data-root D:/model_audit_data
```

`--install-only` prepares or validates the environment without starting services.
`--port` chooses another local port. `--data` changes where cases and results
are stored, and `--venv` selects the launcher-managed environment. `--wheelhouse`
uses prepared installation packages. `--research-data-root` enables only the
four fixed prepared public research profiles described above. Follow the
[setup guide](pipeline-quickstart.md) for their prerequisites.

Press Ctrl+C in the launcher terminal to stop the web service and worker.
Evidence stays in the selected data directory. Restart with the same command and
`--data` value to retain access to earlier cases and runs. Use the download
buttons to copy the evidence you want to share; do not publish confidential
inputs or signing material to GitHub.

## Scope and troubleshooting

- If the launcher rejects an environment, retain the error and choose a fresh
  `--venv` path. It does not silently accept an unrelated or incomplete setup.
- If port 8765 is occupied, use `--port 8766` and open the selected port locally.
- A queued job needs the launcher worker. Run details distinguish queued,
  running, completed and failed jobs. Failed attempts retain evidence; retrying
  creates a new attempt rather than rewriting the original.
- Optional language-model tests require an already installed local Ollama model.
  This walkthrough installs or downloads no language model. The separate
  [garak](production-prd26-garak-adapter.md),
  [scripted PyRIT](production-prd26-pyrit-adapter.md) and
  [adaptive PyRIT](production-prd26-pyrit-adaptive-adapter.md) components need
  their documented runtimes and fixtures; they are not this console walkthrough.

See the [console guide](local-console.md) for service boundaries and the
[production roadmap](production-private-cloud-plan.md) for unresolved agency
acceptance. Demo results and recorded reviews grant no clearance or release
approval.
