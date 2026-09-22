# Government audit integration verification, 22 September 2026

The [update report](../../docs/government-audit-update-2026-09-22.md) describes
the changes and boundaries. The [operating guide](../../docs/government-audit-guide.md)
explains the case review and separate temporal release workflow.

| Run | Result | Evidence |
| --- | --- | --- |
| Final focused integration tests | 133 run, zero failures/errors/skips | [Receipt and implementation hashes](focused-results.json), [test log](focused-tests.log) |
| Broader main suite, research-capable console runtime | 1,201 run, zero failures/errors, two skips | [Full log](full-tests-research-runtime.log) |
| Academic suite, preserved producer runtime | 55 run, zero failures/errors/skips | [Runtime receipt](academic-tests-original-runtime.json), [log](academic-tests-original-runtime.log) |
| Synthetic browser case and current HTTP download | Catalog, record, tamper detection, restart persistence and original cited hash checked | [Browser/HTTP receipt](browser-check.json) |

The focused run follows the final original-hash and server-download additions.
Its source hashes matched before and after execution. The main suite ran earlier
in this integration and includes the first 15 checklist tests; the final focused
run includes all 17 checklist tests. Counts overlap and must not be added as if
they were independent experiments. The main skips are optional ReportLab rendering
and unavailable Windows symlink capability.

These receipts describe the original local workspace, which also contained the
separate academic workstream. They do not claim that every tested study is part
of the government-only GitHub update. In particular, `test_console.py` used CRLF
bytes in that Windows workspace; Git stores its unchanged LF form, so that one
historical test-file hash is not a clean-checkout identity. The separate
[publication verification](../government-publication-20260922/README.md) checks
the exact government files prepared for GitHub. No historical hash was restamped.

The browser download event was observed, and the server attachment was fetched
independently and checked for stale evidence and original hashes. The browser's
saved-file location was not verified. The browser case used synthetic text in a
separate local store; it is not an agency approval record.

Failed setup/replay attempts are retained alongside the corrected runs:

- [Initial main run](full-tests.log): console runtime lacked optional PyTorch,
  producing seven errors; one test still required old README navigation. That
  assertion now verifies the current manuscript and supported links.
- [Academic replay in the older console runtime](academic-tests.log): eight
  XGBoost replay subcases differed because the saved models were produced with
  XGBoost 3.4.1/scikit-learn 1.9.0, whereas this runtime used 2.1.4/1.6.1.
  The preserved `.privacy-venv` matches the producer's versions and passes all
  55 academic tests without refitting or changing evidence.

PowerShell-captured full logs retain their original encoding and local execution
paths. The focused log and JSON receipts use UTF-8. The
[retained-file manifest](retained-files.json) hashes the exact retained bytes;
this index is not part of that manifest. Raw test stores and temporary artifacts
remain under ignored `.local/` and `output/` directories.

These are implementation checks, not general privacy guarantees, an exhaustive
adversary evaluation or institutional release authorization. Historical model
studies retain their own separate assumptions and version-bound replay rules.
