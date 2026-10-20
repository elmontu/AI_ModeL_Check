"""JSON-only, manual captured-input diagnostics; no writes or network."""
from __future__ import annotations

import argparse
import json

from . import check_inputs


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argument errors may contain supplied paths or arbitrary request text.
        raise ValueError("Invalid local integrity command configuration")


def main(argv=None):
    parser = _Parser(add_help=False, allow_abbrev=False)
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--bundle")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--intake-report")
    parser.add_argument("--intake-manifest-sha256")
    parser.add_argument("--handoff-packet")
    parser.add_argument("--handoff-archive-sha256")
    parser.add_argument("--handoff-manifest-sha256")
    try:
        args = parser.parse_args(argv)
        if args.help:
            output = {
                "schema": "local-presentation-integrity-help/1",
                "required_flags": ["--bundle", "--manifest-sha256"],
                "optional_groups": [["--intake-report", "--intake-manifest-sha256"],
                                    ["--handoff-packet", "--handoff-archive-sha256", "--handoff-manifest-sha256"]],
                "packet_requires_intake": True,
                "authorization_effect": "none",
            }
            code = 0
        else:
            output, _, _, _ = check_inputs(args.bundle, args.manifest_sha256, args.intake_report,
                                           args.intake_manifest_sha256, args.handoff_packet,
                                           args.handoff_archive_sha256, args.handoff_manifest_sha256)
            code = 0 if output["result"] == "matches_captured_bytes" else 2
    except ValueError:
        output, code = {"error": "invalid_captured_input_configuration", "authorization_effect": "none"}, 2
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
