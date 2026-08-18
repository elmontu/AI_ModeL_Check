# Release process

Releases are maintainer-controlled and start from a reviewed commit on `main`. A Git tag triggers artifact construction and creates a draft GitHub release; it does not publish to a package index.

## Release gates

1. Confirm the intended public-use licence and disclosure approval. The current repository has no public-use licence.
2. Designate the release owner, code owners, and a private security-reporting channel in repository settings.
3. Update `VERSION` in `src/model_release_assurance/version.py` and add a dated `CHANGELOG.md` entry.
4. Review schema compatibility. Breaking contract changes require a new schema version and migration notes.
5. Run `make check` in a clean environment.
6. Run `python -m build` and `python -m twine check dist/*`.
7. Verify the wheel contains the package, `py.typed`, metadata, and console entry point, but no datasets, reports, credentials, or local paths.
8. Obtain review for changes affecting decision semantics, evidence direction, cryptography, signing, audit records, portfolio composition, or fail-safe behavior.
9. Create a signed or annotated `vX.Y.Z` tag whose version matches the package.
10. Review the draft GitHub release and its generated notes before publication.

## Post-release checks

- Install the wheel in a clean environment and run `mra --help`.
- Validate an example assessment and optimization request.
- Confirm the published artifact hashes match the release workflow output.
- Record any compatibility or security limitation in the release notes.

Publishing to PyPI or another registry is intentionally outside the automated workflow until ownership, credentials, provenance attestation, and rollback policy are approved.
