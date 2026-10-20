"""Command line for local preparation and read-only offline verification."""
from __future__ import annotations
import argparse
import json
from mra_readiness_dashboard.bundle import BundleError
from .packet import BASELINE_PIN, INTAKE_PIN, build_packet, verify_archive


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prepare or verify local review bytes; no acceptance or execution")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Create a new sanitized local preparation directory")
    build.add_argument("--bundle", required=True)
    build.add_argument("--manifest-sha256", required=True)
    build.add_argument("--intake-report", required=True)
    build.add_argument("--intake-manifest-sha256", required=True)
    build.add_argument("--output", required=True)
    verify = sub.add_parser("verify", help="Read bounded packet bytes offline without extraction")
    verify.add_argument("--archive", required=True)
    verify.add_argument("--archive-sha256", required=True)
    verify.add_argument("--manifest-sha256", required=True)
    verify.add_argument("--baseline-manifest-sha256", default=BASELINE_PIN)
    verify.add_argument("--intake-manifest-sha256", default=INTAKE_PIN)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_packet(args.bundle, args.manifest_sha256, args.intake_report, args.intake_manifest_sha256, args.output)
        else:
            checked = verify_archive(args.archive, args.archive_sha256, args.manifest_sha256, args.baseline_manifest_sha256, args.intake_manifest_sha256)
            result = {"schema": "local-review-handoff-verification/1", "result": "verified_local_preparation_bytes",
                      "archive_sha256": checked["_archive_sha256"], "packet_manifest_sha256": checked["_manifest_sha256"],
                      "input_bindings": checked["manifest"]["input_bindings"], "package_status": "prepared_unaccepted",
                      "agency_decisions": "pending", "agency_acceptance": "pending", "authorization_effect": "none",
                      "substantive_open": 12, "substantive_closed": 0, "benchmark_executed": False,
                      "original_source_bytes_verified": False}
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (BundleError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"error": "Local packet preparation or verification rejected; no authority granted"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
