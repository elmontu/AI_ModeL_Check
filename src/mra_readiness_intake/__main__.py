"""Explicit offline checker; all output is a new local preparation receipt."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from .checker import IntakeError, check_intake, write_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    check = subparsers.add_parser('check')
    for name in ('bundle', 'manifest-sha256', 'response', 'response-sha256', 'evidence-root', 'evidence-manifest', 'evidence-manifest-sha256', 'output'):
        check.add_argument('--' + name, required=True)
    check.add_argument('--as-of', default=None, help='Optional timezone-aware ISO checking instant for deterministic receipts')
    args = parser.parse_args(argv)
    try:
        report = check_intake(bundle=args.bundle, manifest_sha256=args.manifest_sha256, response=args.response, response_sha256=args.response_sha256, evidence_root=args.evidence_root, evidence_manifest=args.evidence_manifest, evidence_manifest_sha256=args.evidence_manifest_sha256, as_of=args.as_of)
        pin = write_report(report, args.output, protected_paths=(Path(args.bundle), Path(args.response).parent, Path(args.evidence_manifest).parent, Path(args.evidence_root)))
    except (IntakeError, OSError, TypeError, KeyError, RecursionError):
        print('Evidence intake rejected. No valid completed report was produced.', file=sys.stderr)
        return 2
    print('Local preparation report: ' + report['result'])
    print('Report manifest SHA-256: ' + pin)
    print('Agency decisions pending; 12 substantive gaps remain open; benchmark not executed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
