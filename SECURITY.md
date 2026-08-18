# Security policy

## Supported versions

The current `0.5.x` line is an offline reference release. Security fixes are applied to the latest commit only until a stable release process is established.

## Reporting

Do not place real agency data, model artifacts, credentials, signing keys, attack outputs, or vulnerability details in a public issue. Report through the owning agency's approved security channel and include:

- affected version and deployment identifier;
- whether confidentiality, integrity, availability, authorization, or decision correctness is affected;
- minimal reproduction steps using synthetic data;
- relevant contract, report, manifest, and audit event hashes; and
- any evidence of exploitation.

## Security boundary

The Python package is the assurance decision core. It does not itself sandbox untrusted model deserialization, provide authentication, manage production signing keys, or establish a UC-secure deployment. A service embedding it must implement the controls in `docs/reference/production-roadmap.md`.

Never load pickle, joblib, arbitrary PyTorch checkpoints, or executable model formats in the trusted decision process. Format-specific adapters must run in isolated workers and export inert JSON evidence that is hash-bound to the request.

## Key handling

The CLI's PEM key generation is for development and offline pilots. Production signatures require HSM/KMS-backed non-exportable keys, rotation, revocation, and dual-control policy. Never commit private keys.

## Fail-closed expectations

The following are security defects:

- unknown contract fields being ignored;
- artifact or evidence hash mismatches not stopping the assessment;
- evidence entering a decision under a different metric;
- auditor-only evidence clearing a recipient threat;
- empirical attack failure producing a ceiling;
- invalid accountant scope producing a DP ceiling;
- signature, expiry, or audit-chain failures being treated as warnings; or
- an `inconclusive` mandatory threat producing an overall `clear`.
