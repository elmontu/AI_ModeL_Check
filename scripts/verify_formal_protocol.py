"""Rebuild and audit the machine-checked MRAP core.

This wrapper intentionally delegates proof checking to the Lean kernel.  It
also makes the repository's accepted axiom boundary and toolchain pin
executable in local development and CI.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FORMAL_ROOT = ROOT / "formal" / "lean"
EXPECTED_LEAN_VERSION = "4.32.1"
EXPECTED_THEOREMS = (
    "MRAP.reachable_authorization_integrity",
    "MRAP.active_implies_committed_clear_and_bound",
    "MRAP.step_preserves_release_identity",
    "MRAP.terminal_release_phase_is_absorbing",
    "MRAP.stale_head_second_commit_fails",
    "MRAP.every_step_is_role_authorized",
    "MRAP.reachable_registry_head_never_decreases",
    "MRAP.valid_active_trace_exists",
    "MRAP.Deployment.commit_succeeds_iff_admissible",
    "MRAP.Deployment.successful_commit_is_atomic_and_bound",
    "MRAP.Deployment.committed_request_replay_is_rejected",
    "MRAP.Deployment.used_nonce_commit_is_rejected",
    "MRAP.Deployment.stale_concurrent_commit_is_rejected",
    "MRAP.Deployment.activation_succeeds_iff_current_record_admissible",
    "MRAP.Deployment.successful_activation_can_serve",
    "MRAP.Deployment.can_serve_implies_current_live_bound_authorization",
    "MRAP.Deployment.artifact_substitution_cannot_be_served",
    "MRAP.Deployment.interface_substitution_cannot_be_served",
    "MRAP.Deployment.stale_gateway_cannot_serve",
    "MRAP.Deployment.expired_lease_cannot_serve",
    "MRAP.Deployment.authorization_deadline_cannot_serve",
    "MRAP.Deployment.revocation_stops_existing_gateway",
    "MRAP.Deployment.suspension_stops_existing_gateway",
    "MRAP.Deployment.reachable_active_has_serving_realization",
    "MRAP.Deployment.ideal_commit_and_activation_are_executable",
    "MRAP.Security.successful_acceptance_is_authenticated_authorized_and_bound",
    "MRAP.Security.accepted_envelope_replay_is_rejected",
    "MRAP.Security.mismatched_artifact_is_rejected",
    "MRAP.Security.compromised_signer_is_rejected",
    "MRAP.Security.expired_envelope_is_rejected",
    "MRAP.Security.authenticated_step_requires_a_bound_message",
    "MRAP.Security.authenticated_reachable_projects",
    "MRAP.Security.authenticated_reachable_authorization_integrity",
    "MRAP.Security.authenticated_active_implies_committed_clear_and_bound",
    "MRAP.Statistics.finite_false_authorization_bound",
    "MRAP.Statistics.finite_false_authorization_within_budget",
    "MRAP.Statistics.rational_experiment_false_authorization_within_budget",
    "MRAP.Statistics.registered_component_budget_controls_false_authorization",
    "MRAP.Mutants.direct_unsafe_activation_is_rejected",
)
ALLOWED_AXIOMS = frozenset({"propext", "Quot.sound"})
PLACEHOLDER = re.compile(r"\b(?:sorry|admit)\b")
AXIOM_LINE = re.compile(
    r"^'(?P<theorem>[^']+)' depends on axioms: \[(?P<axioms>.*)\]$"
)
NO_AXIOM_LINE = re.compile(
    r"^'(?P<theorem>[^']+)' does not depend on any axioms$"
)


def _run(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=FORMAL_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.stdout:
        console_encoding = sys.stdout.encoding or "utf-8"
        console_text = completed.stdout.encode(
            console_encoding, errors="replace"
        ).decode(console_encoding)
        print(console_text, end="")
    if completed.returncode:
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}: "
            + " ".join(command)
        )
    return completed.stdout


def _find_lake(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("MRA_LAKE") or shutil.which("lake")
    if not candidate:
        raise RuntimeError(
            "Lake was not found. Install the pinned Lean toolchain or pass --lake."
        )
    return candidate


def _reject_source_placeholders() -> None:
    violations: list[str] = []
    for source in sorted(FORMAL_ROOT.rglob("*.lean")):
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if PLACEHOLDER.search(line):
                violations.append(f"{source.relative_to(ROOT)}:{line_number}")
    if violations:
        raise RuntimeError(
            "Lean proof placeholders are forbidden: " + ", ".join(violations)
        )


def _audit_axiom_output(output: str) -> None:
    found: dict[str, frozenset[str]] = {}
    for line in output.splitlines():
        stripped = line.strip()
        no_axiom_match = NO_AXIOM_LINE.match(stripped)
        if no_axiom_match:
            found[no_axiom_match.group("theorem")] = frozenset()
            continue
        match = AXIOM_LINE.match(stripped)
        if not match:
            continue
        raw_axioms = match.group("axioms").strip()
        axioms = frozenset(
            item.strip() for item in raw_axioms.split(",") if item.strip()
        )
        found[match.group("theorem")] = axioms

    missing = sorted(set(EXPECTED_THEOREMS) - set(found))
    if missing:
        raise RuntimeError("missing theorem audit output: " + ", ".join(missing))

    disallowed = {
        theorem: sorted(axioms - ALLOWED_AXIOMS)
        for theorem, axioms in found.items()
        if theorem in EXPECTED_THEOREMS and axioms - ALLOWED_AXIOMS
    }
    if disallowed:
        details = "; ".join(
            f"{theorem}: {', '.join(axioms)}"
            for theorem, axioms in sorted(disallowed.items())
        )
        raise RuntimeError("unapproved Lean axioms: " + details)


def verify(lake: str) -> None:
    _reject_source_placeholders()
    version = _run([lake, "env", "lean", "--version"])
    if f"version {EXPECTED_LEAN_VERSION}" not in version:
        raise RuntimeError(
            f"expected Lean {EXPECTED_LEAN_VERSION}; received: {version.strip()}"
        )
    _run([lake, "build"])
    audit_output = _run([lake, "env", "lean", "Main.lean"])
    _audit_axiom_output(audit_output)
    print("Formal MRAP verification passed with the approved axiom boundary.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", help="path to the Lake executable")
    args = parser.parse_args(argv)
    try:
        verify(_find_lake(args.lake))
    except (OSError, RuntimeError) as exc:
        print(f"formal verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
