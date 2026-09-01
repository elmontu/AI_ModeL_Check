# Release process

Releases are maintainer-controlled and start from a reviewed commit on `main`. A Git tag reruns the formal proof gate, Python checks, schema and link replay, and wheel validation before creating a draft GitHub release. It does not publish to a package index.

## Release gates

1. Confirm the intended public-use licence and disclosure approval. The current repository has no public-use licence.
2. Designate the release owner and required reviewers, and configure a private security-reporting channel in repository settings. Add `CODEOWNERS` only after the responsible maintainers are confirmed.
3. Update `VERSION` in `src/model_release_assurance/version.py` and add a dated `CHANGELOG.md` entry.
4. Review schema compatibility. Breaking contract changes require a new schema version and migration notes. Never regenerate a retained historical schema from the current model. Regenerate `schemas/current-schema-manifest-v1.json` after all current schema bytes are final.
5. Run `make verify` in a clean environment so Python, schema, documentation-link, regression, and Lean proof checks all pass.
6. Run `python -m build` and `python -m twine check dist/*`.
7. Install the wheel outside the checkout and run `mra --version`, example validation, and schema-generation smoke tests. Verify that it contains the package, `py.typed`, metadata, and console entry point, but no datasets, reports, credentials, or local paths.
8. Obtain review for changes affecting decision semantics, evidence direction, cryptography, signing, audit records, portfolio composition, or fail-safe behavior.
9. Create a signed or annotated `vX.Y.Z` tag whose version matches the package.
10. Review the draft GitHub release and its generated notes before publication.

The committed schema manifest is an unsigned, deterministic source inventory; it is not a release attestation. Before production publication, a protected release identity must sign or externally attest the exact manifest bytes and publish the signature plus signer/public-key or certificate reference. No signing private key belongs in this repository.

## Post-release checks

- Install the wheel in a clean environment and run `mra --help`.
- Validate an example assessment and optimization request.
- Confirm the published artifact hashes match the release workflow output.
- Record any compatibility or security limitation in the release notes.
- Preserve the released wheel, dependency lock, schemas, replay fixtures, verification profile, trust metadata, and artifact hashes for the full records-retention period; the current CLI is not yet a version-dispatched historical verifier.

Publishing to PyPI or another registry is intentionally outside the automated workflow until ownership, credentials, provenance attestation, and rollback policy are approved.
