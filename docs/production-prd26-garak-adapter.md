# PRD-26: scoped garak prompt-injection adapter

Status: **in progress**. This is a local synthetic engineering milestone for
PRD-26. Agency endpoint approval, infrastructure qualification, independent
scientific/security/license review and PyRIT multi-turn integration remain
pending. No result grants assessment, clearance, release or delivery authority.

## Declared upstream path and corpus

The adapter calls the unmodified garak 0.17.0
`promptinject.HijackLongPrompt.probe(generator)` and
`promptinject.AttackRogueString.detect(attempt)` implementations. It selects
indices **0, 4, 8 and 12** from the bundled 700-prompt corpus before any target
call, preserving aligned original prompts, triggers and legacy settings. These
are four different attack templates within the first grammar context; they are
not independent statistical trials or coverage of all 700 prompts.

The public test corpus is derived from the bundled PromptInject resources by
Agency Enterprise, LLC. Its [MIT notice](../tests/fixtures/garak_promptinject_corpus.LICENSE.txt)
is retained for those records; this does not select a licence for the application.

The same four records run through three application wrappers: a direct user
prompt, a synthetic retrieved-document summary and an inert agent-document
summary. The original upstream prompt and the actual target messages are both
retained. Neither document wrapper uses a live retrieval index. No tool or
simulated action is executed. Legacy upstream generation settings remain
provenance only; the actual Ollama options are declared separately.

The single allowed target is the already installed `qwen2.5-coder:14b` at
`http://127.0.0.1:11434`, with observed local digest
`9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849`.
The worker verifies inventory before and after execution. This local inventory
binding is not remote host attestation. A different endpoint or model requires
a separately reviewed profile; no model download or external API spend occurs.

## Controls, scoring and incomplete outcomes

There are **12 target probe attempts**, 12 deliberately vulnerable scripted
controls, 12 defended scripted controls and six actual target echo calibrations.
The six endpoint calibrations repeat the benign and unprotected trigger echoes
for each interface label; they do not qualify the document wrappers. Scripted
controls exercise the same real upstream probe and detector path, but they are
not realistic trained control models. Six additional lexical scorer cases
check presence, absence, case, quotation, partial and encoded text.

The detector and independent replay measure **case-insensitive literal presence**
of the declared rogue string. Quotations and negations containing that string
also count; partial, encoded and semantic disclosures can be missed. Human
review is explicitly pending. A zero count is not a privacy ceiling or a
model-safety verdict. Training-record extraction is outside this fixture.

Empty, malformed, incomplete, length-stopped, transport-error or mismatched
responses remain unscoreable. Their retained text and observed trigger presence
are kept, even when no score can be accepted. Failed controls, unstable inventory
or missing attempts make the campaign incomplete; no fallback attack is used.

## Runtime, process and evidence boundary

[The component lock](../deploy/garak/windows-cp312.json) records the CPython
3.12.14 Windows runtime and 41 exact distribution versions and artifact hashes.
All 335 upstream garak package files, the METADATA hash and matching package
RECORD entries are verified before and after the worker operation. The official garak wheel is
unmodified. `langdetect` is a local wheel built from the hash-verified public
1.0.9 source archive; the lock records its source, builder and actual artifact
hash. It is not presented as an official upstream wheel.

This is an explicit **component runtime**, installed with `--no-deps` from the
locked closure. The full upstream dependency set, CLI, unselected plugins,
cloud SDKs and model-loading dependencies are unsupported. The lock retains
upstream dependency declarations and omissions. Do not use `pip check` success
or full-scanner availability as an acceptance claim for this partial closure.
The existing console and earlier adapter environments remain separate.

A preparation worker creates the exact upstream plan without target calls.
The parent freezes it before launching the execution worker, which regenerates
and compares the same corpus. Source, lock, model, inference, runtime and plan
bindings are checked along with independently replayed retained transcripts,
upstream attempt metadata, scores and persisted process receipts.

The Windows owned process uses a Job Object and a gated isolated Python startup,
with output limits and a maximum 600-second parent deadline for each worker. Child configuration,
cache, log, application-data and temporary directories stay inside its fresh
D: output. Credentials and proxy settings are not forwarded. The transport
allows only loopback inventory and chat paths, rejects proxies and redirects,
and permits at most 18 inference calls. Each request uses a 60-second socket
inactivity timeout and the campaign checks its 480-second budget between reads.
These are not strict server execution deadlines. Killing the worker does not
attest that the separate Ollama service has stopped computing.

`hostile_code_isolated`, `network_isolated`, `filesystem_isolated` and
`resource_limits_verified` remain false. Application endpoint checks are not
verified network isolation. All assessment and authorization flags remain false.
This separate adapter neither changes the native nine-probe console runner nor
widens the old two-tool assessment catalog or the console discovery contract.

## Run and inspect

Prepare a fresh component environment and a wheelhouse containing every artifact
in the lock, including the declared locally built `langdetect` wheel. Both the
parent console Python and component environment must use Windows CPython
3.12.14 from the same base interpreter. Reuse none of the earlier runtime
directories. From this government checkout:

```powershell
& .\.venv-pipeline\Scripts\python.exe -B -m venv --without-pip .local/garak-env-v1
& .\.venv-pipeline\Scripts\python.exe -B -m pip --python .local/garak-env-v1/Scripts/python.exe install --no-index --no-deps --no-compile --require-hashes --find-links PATH_TO_VERIFIED_WHEELHOUSE -r deploy/garak/windows-cp312.requirements.txt
& .\.venv-pipeline\Scripts\python.exe -B scripts/rehearse_garak_adapter.py --python .local/garak-env-v1/Scripts/python.exe --output .local/garak-v1
```

The declared model must already be installed and served locally. Output must be
a fresh ignored `.local` directory beneath this repository. Inspect the complete
plan, responses, controls, lexical findings, replay and process receipts. A
completed campaign means its declared fixture executed and replayed, not that
the model or an agency deployment passed acceptance.

## Local validation and next work

Source and installed-wheel campaigns each completed all 12 local target probes
with zero unscoreable responses and passed the 24 scripted controls, six endpoint
calibrations and six upstream lexical scorer cases. Independent retained
transcript, attempt, score and process replay passed. Each run observed literal
marker presence in **8 of 12** responses: direct 3/4, synthetic document 4/4 and
inert agent-document 1/4. These are literal observations, including possible
quotations or negations, not eight independently confirmed security compromises.
Human/semantic review remains pending; no risk clearance is produced.

Additional offline fixtures used the real upstream probe and detector with
scripted transport failures and truncated marker replies. Both remained
incomplete with one unscoreable attempt; the truncated marker observation was
retained. These checks made zero target network calls.

The installed application imported its workflow from the new environment's
site-packages, with no repository source imports. All 205 packaged files matched
the frozen source bytes. The 151 new garak tests passed without skips. The full
required government suite passed **2,207 tests across 121 modules**, with zero
failures, errors, skips, expected failures or unexpected successes in 1,141.984
seconds. All 485 required source hashes match the final implementation. Schema
verification preserved all 37 bindings; local links in 74 Markdown files passed.
All 958 earlier tracked files outside the seven intended documentation/test-runner/
positive-test updates remain byte-identical, including every prior production
source file and the frozen advisory.

The first full run retained one error in an earlier positive lifecycle test:
its real elapsed clock reached the unchanged activation/grant expiry during
expensive local checks, and delivery was correctly denied. Long and short temp
paths reproduced the same boundary. That positive test now uses a controlled
fixture clock, with its explicit `advance_to(expiry)` and separate deadline
regressions preserved. Process timeouts, production clocks, guards and TTLs
remain unchanged. This is fixture correctness validation, not real-time latency
or agency performance qualification. Failed receipts remain available.

Validation receipts are retained under
`.local/verification/prd26-garak-20261006/`. Earlier source-bound receipts remain
intact, including the failed initial preparation/import diagnostic.

The next scoped PRD-26 milestone is **PyRIT multi-turn orchestration**, with
separate target/attacker/scorer identities, bounded retries and retained
conversation-state replay. Agency endpoint approval, real RAG/agent interfaces,
independent semantic/human scoring, realistic controls and private-cloud worker
isolation remain open. PRD-27 expansion follows those separately qualified
profiles; this milestone does not declare production readiness.

Primary upstream references: [garak 0.17.0 package](https://pypi.org/project/garak/0.17.0/)
and [upstream source](https://github.com/NVIDIA/garak).
