#!/usr/bin/env python3
"""Independently replay a saved inert native adapter candidate and scored evidence."""
from pathlib import Path
import argparse
import json
import sys
ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from model_release_assurance.production_adapters.native import replay_run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    args=parser.parse_args(argv)
    try:
        report=replay_run(args.run)
    except (ValueError, OSError, TypeError) as error:
        print(json.dumps({"status":"failed", "reason":type(error).__name__, "authorization_eligible":False}))
        return 1
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report.get("status") in {"passed", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
