## Summary

Describe the change, whether it affects the reference core or evidence lab, and the affected contract or component.

## Security and compatibility

- [ ] Evidence direction is unchanged or explicitly reviewed.
- [ ] Artifact, interface, population, policy, and portfolio bindings are preserved.
- [ ] Schema compatibility is preserved, or the migration and retained-version impact is documented.
- [ ] Assessment recommendations are not presented as production authorization.
- [ ] No generated output, model artifacts, confidential data, or secrets are committed.

## Verification

- [ ] `make check`
- [ ] `make verify` was run for formal/protocol changes, or the reason it is not applicable is stated.
- [ ] Relevant schemas and examples were regenerated and reviewed.
- [ ] Distribution build and wheel smoke tests were run for packaging changes.
- [ ] User-visible changes are recorded in `CHANGELOG.md`.
- [ ] Package contents and public documentation contain no machine-specific paths.

## Release note

State the user-visible effect in one sentence, or write `No release note` with a reason.
