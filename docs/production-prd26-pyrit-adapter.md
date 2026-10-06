# PRD-26: scoped PyRIT multi-turn adapter

Status: **in progress**. This is a local synthetic engineering milestone within
PRD-26. Agency endpoint approval, infrastructure qualification, independent
scientific/security/license review and semantic human review remain pending.
No result grants assessment, clearance, release or delivery authority.

## Declared upstream path

The adapter uses the unmodified [PyRIT 1.1.0 package](https://pypi.org/project/pyrit/1.1.0/)
and its real `RedTeamingAttack`, `PromptNormalizer`, `SQLiteMemory` and
`SubStringScorer` components. The attacker, objective target and scorer have
separate identifiers. Conversation state, normalized prompts, memory records,
turn scores, upstream results and stopping decisions are retained for replay.
The attacker system message retains upstream's null content hashes; separate
recomputed text hashes support independent replay without rewriting provenance.

Two fixed public synthetic objectives exercise direct chat and a synthetic
document context. Each is limited to three target turns. A fixed scripted
attacker supplies the prompt sequence through PyRIT's actual orchestration loop.
This exercises multi-turn orchestration; it does not qualify an adaptive model
attacker, an LLM judge, a live retrieval index or an executable agent.
No private training records, agency datasets, cloud credentials or tools are used.

The single allowed real target is the already installed `qwen2.5-coder:14b` at
`http://127.0.0.1:11434`, with observed local digest
`9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849`.
Inventory is bound before and after the campaign. This local binding is not
remote host attestation. Changing endpoint, model or objective requires a
separately reviewed profile. There is no model download or external API spend.

## Controls and interpretation

Each objective also executes a scripted positive control and a scripted null
control through the same upstream path. The positive control reaches its public
marker on turn two and must stop. The null control must exhaust all three turns.
These are orchestration fixtures, not trained control models or population studies.

`SubStringScorer` uses `ExactTextMatching(case_sensitive=True,
ignore_whitespace=False)`. Independent replay checks literal marker presence.
Quoted or negated text containing the marker still matches. Case changes,
encoding, partial disclosures and semantic paraphrases can evade this scorer.
Human review remains pending. Neither zero marker matches nor passed controls
establishes a privacy ceiling, a model-safety verdict or training-data protection.

Invalid, malformed, incomplete, truncated or transport-error responses remain
incomplete and unscoreable. Retained text and observed literal hits stay visible.
Upstream removes a processing-error response and its adjacent failed request
from later target wire history. Independent replay checks that projection while
retaining the full original memory and the undetermined score.
Replay rejects altered prompts, scores, histories, role identifiers, controls,
plan bindings, stopping rules or persisted process records. No substitute attack
or unsupported-path pass is supplied.

## Runtime and storage boundary

[The component lock](../deploy/pyrit/windows-cp312.json) declares Windows CPython
3.12.14 and 52 exact public wheel artifacts, including the pandas closure
required when the actual upstream scorer is constructed. All 1,620 upstream PyRIT package files,
its METADATA hash and matching package RECORD entries are checked before and
after worker execution. The official PyRIT wheel remains unmodified. The lock
records upstream requirements and 58 omitted requirement strings, including
optional extras. The full dependency set, CLI, other attacks, cloud targets and
multimodal components are unsupported in this explicit component runtime.

Windows `appdirs` reads shell folder locations rather than the redirected AppData
environment. The trusted adapter therefore applies a narrow `user_data_dir` hook
before any PyRIT import, admitting only PyRIT's two fixed data/cache names under
the fresh D: worker cache. The official appdirs file, METADATA, RECORD and module
origin are checked. The resulting PyRIT data, cache and log paths are verified
and retained. This is an intentional runtime hook, not filesystem isolation.
Initial import diagnostics that exposed the shell-folder behavior are preserved
as nonqualifying evidence; accepted campaign receipts require the D: path binding.

The Windows owned process uses a Job Object and gated isolated Python startup.
Each worker has a maximum 600-second parent deadline and bounded input/output.
Retry counts are set to one before upstream imports; local counters bound
attacker/target calls and message/history size. Credentials and proxy variables
are not forwarded. The application transport permits only fixed loopback paths,
rejects redirects and proxies, and retains model response bindings. A socket
inactivity timeout and campaign budget do not attest server execution deadlines.
The separate Ollama server remains outside the owned Job Object.

`hostile_code_isolated`, `network_isolated`, `filesystem_isolated` and
`resource_limits_verified` remain false. All assessment, clearance and delivery
flags remain false. This adapter does not widen the native console runner,
the old two-tool assessment catalog or the console discovery contract.

## Local setup

Create a new environment with the existing Windows CPython 3.12.14 console
interpreter. Keep the console and earlier SACRO-ML, ART and garak runtimes intact.
Install this explicit component closure from a verified wheelhouse:

```powershell
.venv-pipeline\Scripts\python.exe -B -m venv --without-pip .local\pyrit-runtime
.venv-pipeline\Scripts\python.exe -B -m pip --python .local\pyrit-runtime\Scripts\python.exe install --no-index --no-deps --no-compile --require-hashes --find-links .local\pyrit-wheelhouse -r deploy\pyrit\windows-cp312.requirements.txt
.venv-pipeline\Scripts\python.exe -B scripts\rehearse_pyrit_adapter.py --python .local\pyrit-runtime\Scripts\python.exe --output .local\pyrit-campaign
```

The driver requires a fresh ignored output under this government repository.
An unavailable declared dependency, changed wheel/source binding or incomplete
campaign returns nonzero. `pip check` success and general scanner availability
are not acceptance claims for this partial runtime.

## Validation and remaining acceptance

Source and installed-wheel campaigns each executed six upstream campaigns
with four real local-model turns. Positive controls stopped at turn two, null controls exhausted
three turns, and all seven lexical calibrations and independent history/score
replay passed. Two real target responses contained the public literal marker;
these are emission diagnostics, not confirmed security compromises.

Two additional actual upstream fixtures used scripted client responses and zero
provider calls. A first transport failure and a first truncated marker response
each remained incomplete with five scored and one unscoreable target response.
The truncated marker stayed observed and retained with an undetermined/None
score. Earlier import and normalization diagnostics are preserved; final runs
use the corrected source.

On 6 October 2026 the required government profile passed **2,345 tests across
127 modules**, with zero failures, errors, skips, expected failures or unexpected
successes. All 502 recorded source hashes still match. The six new PyRIT suites
passed 138 tests. Checks verified 37 unchanged schemas and links in 75 Markdown
files. Installed application imports came from the new runtime's site-packages;
the government source directory was not imported. The verified wheel contains
213 application package files. A final README metadata rebuild preserves those
same tested package bytes.

The source campaign, installed-wheel campaign and both final negative fixtures
share application source binding
`adf6339180d1900774add91b8363c5a708331a058808a42f0f2f2daf5b6d90e1`.
The component lock SHA-256 is
`e93ffeb365b3fa36f026d035a42fdda6f817dd94c4f20ee800428a059e314b26`.
Receipts, verified public wheels and preliminary diagnostics remain in the
ignored D: directory `.local/verification/prd26-pyrit-20261006/`.
They are local source-bound evidence, not an independently hosted agency bundle.
All prior implementation and frozen advisory bytes remain unchanged. Earlier
[garak](production-prd26-garak-adapter.md) and
[ART](production-prd25-art-adapter.md) receipts remain bound to their own sources.

PRD-26 remains in progress. Agency target approval, semantic/human adjudication,
adaptive attacker qualification, live RAG/tool boundaries, infrastructure
isolation, independent security/scientific review and operational acceptance
require separate evidence. Provider and hosting region remain open. No private
data production intake or deployment is authorized by this local fixture.
