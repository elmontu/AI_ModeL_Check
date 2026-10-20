"""Fixed diagnostics for existing pinned readers, without authority or repair."""
from __future__ import annotations

from datetime import datetime, timezone

from mra_readiness_dashboard.bundle import load_snapshot
from mra_readiness_intake.report import load_report
from mra_readiness_handoff.packet import load_packet


def _configuration(bundle, manifest_sha256, intake_report, intake_manifest_sha256,
                   handoff_packet, handoff_archive_sha256, handoff_manifest_sha256):
    intake_options = (intake_report, intake_manifest_sha256)
    packet_options = (handoff_packet, handoff_archive_sha256, handoff_manifest_sha256)
    partial = lambda values: any(value is not None for value in values) and not all(value is not None for value in values)
    if (bundle is None or manifest_sha256 is None or partial(intake_options)
            or partial(packet_options) or (handoff_packet is not None and intake_report is None)):
        raise ValueError("Incomplete captured-input configuration")


def check_inputs(bundle, manifest_sha256, intake_report=None, intake_manifest_sha256=None,
                 handoff_packet=None, handoff_archive_sha256=None, handoff_manifest_sha256=None,
                 *, _readers=None):
    """Reread configured inputs in dependency order; return safe report and data.

    The report contains fixed identifiers and states only. Returned artifacts are
    for existing guarded presentation routes and must never be embedded in status
    responses. The optional reader tuple is an internal code seam, not a CLI or
    configuration input. No reader runs after a failed prerequisite.
    """
    _configuration(bundle, manifest_sha256, intake_report, intake_manifest_sha256,
                   handoff_packet, handoff_archive_sha256, handoff_manifest_sha256)
    if _readers is None:
        readers = (load_snapshot, load_report, load_packet)
    elif isinstance(_readers, tuple) and len(_readers) == 3 and all(callable(reader) for reader in _readers):
        readers = _readers
    else:
        raise ValueError("Invalid captured-input reader configuration")
    definitions = (
        ("readiness_bundle", True, (bundle, manifest_sha256)),
        ("intake_report", intake_report is not None, (intake_report, intake_manifest_sha256, manifest_sha256)),
        ("review_packet", handoff_packet is not None,
         (handoff_packet, handoff_archive_sha256, handoff_manifest_sha256, manifest_sha256, intake_manifest_sha256)),
    )
    components, values = [], [None, None, None]
    prerequisites_match = True
    for index, (identifier, configured, arguments) in enumerate(definitions):
        if not configured:
            state, code = "not_configured", "not_configured"
        elif not prerequisites_match:
            state, code = "not_checked", "prerequisite_unavailable"
        else:
            try:
                values[index] = readers[index](*arguments)
            except Exception:
                # Neither exception text nor input identifiers belong in status.
                state, code = "unavailable", "validation_failed"
                prerequisites_match = False
            else:
                state, code = "matches_captured_bytes", "captured_bytes_match"
        components.append({"id": identifier, "state": state, "code": code})
    report = {
        "schema": "local-presentation-integrity-status/1",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "check_scope": "configured_captured_inputs_only",
        "result": "matches_captured_bytes" if prerequisites_match else "unavailable",
        "components": components,
        "agency_decisions": "pending",
        "authorization_effect": "none",
        "readiness_or_acceptance_established": False,
    }
    return report, *values
