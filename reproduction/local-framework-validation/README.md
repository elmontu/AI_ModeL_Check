# Retained local framework verification

These results were produced on 10 September 2026. Execution success is not a
model safety certification or release authorization.

- [Detailed verification and remaining scope](../../docs/framework-e2e-validation-2026-09-10.md)
- [Every option and adversary result](validation-report.md)
- [Full metrics and source/runtime bindings](validation-report.json)
- [Main test log](full-test-suite.log)
- [Academic test log](academic-tests.log)
- [Fresh installation log](fresh-setup.log)
- [Optional CPU runtime](optional-runtime/runtime.json)
- [Optional focused test results](optional-runtime/focused-results.json)
- [SHA-256 of retained result/log files](retained-files.json)

Raw job artifacts remain in ignored local `output/framework-e2e-final-20260910/`.
The JSON stores job IDs relative to that run's workspace; it does not claim those
jobs are present in the separate interactive console store. The optional test
logs retain the original execution paths from the earlier validation directory.
The source CLI can regenerate the entire public-data matrix into a new directory.
