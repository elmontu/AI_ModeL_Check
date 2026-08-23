"""Run the reproducible MRAP adversarial-mutation evaluation.

The suite reports whether every unsafe transcript mutation is rejected and
whether both structural and authenticated controls remain accepted.  It is a
protocol robustness evaluation, not evidence that the model-risk tests are
scientifically complete.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
for search_path in (ROOT, ROOT / "src"):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from tests.test_release_protocol import ReleaseProtocolTests  # noqa: E402


CONTROL_TESTS = (
    "test_complete_lifecycle_reaches_active",
    "test_authenticated_profile_verifies_every_actor_and_artifact",
)

MUTATION_TESTS = (
    "test_failed_atomic_commit_cannot_authorize_or_activate",
    "test_hash_chain_tampering_is_detected",
    "test_incomplete_evidence_cannot_progress",
    "test_wrong_artifact_producer_role_is_detected",
    "test_protocol_artifacts_cannot_escape_the_declared_bundle",
    "test_current_status_replay_rejects_an_expired_active_claim",
    "test_event_rejects_payload_fields_from_another_message_type",
    "test_reject_requires_exhaustive_search_replay",
    "test_registry_sequence_must_strictly_advance",
    "test_monitoring_report_cannot_self_authorize_revocation",
    "test_authenticated_profile_rejects_event_tampering",
    "test_authenticated_profile_rejects_artifact_tampering",
    "test_authenticated_profile_rejects_cross_release_replay",
    "test_authenticated_profile_rejects_compromised_key",
    "test_authenticated_profile_rejects_untrusted_signers",
    "test_caller_can_forbid_authenticated_profile_downgrade",
    "test_unexpected_artifact_kind_is_rejected",
    "test_duplicate_artifact_kind_is_rejected",
    "test_early_expiry_event_is_rejected",
)


def _run_case(name: str) -> tuple[bool, str]:
    stream = StringIO()
    suite = unittest.TestSuite([ReleaseProtocolTests(name)])
    with redirect_stdout(stream), redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    return result.wasSuccessful(), stream.getvalue().strip()


def evaluate() -> dict[str, object]:
    controls = []
    for name in CONTROL_TESTS:
        passed, detail = _run_case(name)
        controls.append({"test": name, "accepted_as_expected": passed, "detail": detail})

    mutations = []
    for name in MUTATION_TESTS:
        passed, detail = _run_case(name)
        mutations.append({"test": name, "rejected_as_expected": passed, "detail": detail})

    killed = sum(bool(item["rejected_as_expected"]) for item in mutations)
    controls_passed = all(bool(item["accepted_as_expected"]) for item in controls)
    return {
        "schema_version": "1.0",
        "evaluation": "MRAP authenticated/structural adversarial mutation suite",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "controls_passed": controls_passed,
        "control_count": len(controls),
        "unsafe_mutant_count": len(mutations),
        "unsafe_mutants_rejected": killed,
        "mutation_score": killed / len(mutations),
        "valid": controls_passed and killed == len(mutations),
        "controls": controls,
        "mutations": mutations,
        "non_claim": (
            "This evaluates transcript enforcement and signature binding only; it does not "
            "establish scientific test adequacy or implementation refinement."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
