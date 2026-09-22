"""Operator commands for the bounded, public-synthetic export demonstration."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .store import ExportDenied, ExportStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mra export", description="Synthetic-only two-release model export POC"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name: str, help_text: str, *, data: bool = True):
        item = commands.add_parser(name, help=help_text)
        if data:
            item.add_argument("--data", type=Path, default=Path(".local/model-export-poc"))
        return item

    serve = command("serve", "serve the local test UI and API; initialize only a new directory")
    serve.add_argument("--port", type=int, default=8767)
    serve.add_argument("--repository", type=Path,
                       help="existing source repository containing retained temporal research reports")
    serve.add_argument("--temporal-run", type=Path,
                       help="existing verified temporal run directory; never initializes a study")
    serve.add_argument("--temporal-operator", type=Path,
                       help="existing initialized operator directory containing workflow.json and assurance.sqlite3")
    command("init", "explicitly initialize a new synthetic test history")
    command("status", "read an existing history without modifying its files")
    command("verify-history", "check an existing history; does not authorize a release")
    plan = command("plan", "inspect the DP contract for a next action without constructing a model")
    plan.add_argument("--route", choices=("first", "reuse", "retained-state", "independent", "central-count"), required=True)
    command("catalog", "describe supported constructions and their scope", data=False)
    inspect = command("inspect-bundle", "check bundle structure, not its production provenance", data=False)
    inspect.add_argument("--input", type=Path, required=True)

    prepare = command("prepare", "stage a model internally using an idempotency key")
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument("--stage", type=int, choices=(1, 2), required=True)
    prepare.add_argument("--route", choices=("first", "retained-state", "independent", "central-count"), required=True)
    prepare.add_argument("--expected-revision", type=int, required=True)
    commit = command("commit", "atomically commit a staged model against the current history")
    commit.add_argument("--request-id", required=True)
    commit.add_argument("--expected-revision", type=int, required=True)
    download = command("download", "write exact committed bytes to a new file")
    download.add_argument("--release-id", required=True)
    download.add_argument("--output", type=Path, required=True)
    evaluate = command("evaluate", "evaluate a committed model on the fixed public synthetic holdout")
    evaluate.add_argument("--release-id", required=True)
    revoke = command("revoke", "stop future downloads; preserve disclosure and privacy cost")
    revoke.add_argument("--release-id", required=True)
    return parser


def service_paths(args) -> dict[str, Path]:
    """Validate explicit configuration without opening or creating a registry.

    File presence is only a setup check. The web adapter still checks evidence,
    inventory, ledger and artifact bindings before making anything available.
    """
    options = {}
    required = {
        "repository": (),
        "temporal_run": ("registration.json", "results.json", "completion.json"),
        "temporal_operator": ("workflow.json", "assurance.sqlite3"),
    }
    for name, files in required.items():
        value = getattr(args, name)
        if value is None:
            continue
        path = value.resolve()
        flag = "--" + name.replace("_", "-")
        if not path.is_dir():
            raise ValueError(f"{flag} needs an existing directory: {path}. No registry was initialized.")
        missing = [name for name in files if not (path / name).is_file()]
        if missing:
            raise ValueError(f"{flag} is missing {', '.join(missing)}: {path}. "
                             "Select an existing verified run or initialized operator directory; "
                             "no registry was initialized.")
        options[name] = path
    return options


def warn_missing_temporal_defaults(options: dict[str, Path]) -> None:
    """Keep the historical launcher usable while making unavailable data clear."""
    from ..temporal_assurance.web import DEFAULT_ROOT
    defaults = (
        ("temporal_run", "evidence replay", DEFAULT_ROOT / "run-v1",
         ("registration.json", "results.json", "completion.json")),
        ("temporal_operator", "release workflow", DEFAULT_ROOT / "operator-workflow-v1",
         ("workflow.json", "assurance.sqlite3")),
    )
    for name, label, path, files in defaults:
        if name not in options and not all((path / name).is_file() for name in files):
            flag = "--" + name.replace("_", "-")
            print(f"Temporal {label} is unavailable at the historical default {path}. "
                  f"Use {flag} EXISTING_DIRECTORY to select retained data. "
                  "The separate /synthetic lab can still run; no temporal registry is initialized.",
                  file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    # Preserve the original module launcher: --data DIR --port PORT.
    if not tokens or tokens[0] in {"--data", "--port"}:
        tokens.insert(0, "serve")
    parser = build_parser()
    args = parser.parse_args(tokens)
    try:
        if args.command == "serve":
            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            options = service_paths(args)
            try:
                import uvicorn
                from .api import create_app
            except ImportError as exc:
                raise RuntimeError("The HTTP service needs the optional console dependencies.") from exc
            warn_missing_temporal_defaults(options)
            uvicorn.run(create_app(args.data, **options), host="127.0.0.1", port=args.port, access_log=False)
            return 0
        if args.command == "catalog":
            from .tools import export_construction_catalog
            result = export_construction_catalog()
        elif args.command == "inspect-bundle":
            from .tools import ExportToolService
            if args.input.stat().st_size > 16 * 1024:
                raise ValueError("Bundle exceeds the 16 KiB inspection limit.")
            content = args.input.read_bytes()
            result = ExportToolService(Path.cwd()).inspect_export_bundle(content.decode("utf-8"))
        elif args.command == "init":
            if args.data.exists() and (not args.data.is_dir() or any(args.data.iterdir())):
                raise ValueError("Initialization requires a new or empty synthetic-test directory.")
            result = ExportStore(args.data).status()
        elif args.command in {"status", "verify-history", "plan"}:
            store = ExportStore.open_read_only(args.data)
            if args.command == "plan":
                from .protocol import plan_export
                result = plan_export(store.status(), args.route)
            else:
                result = store.status() if args.command == "status" else store.verify_history()
        else:
            store = ExportStore.open_existing(args.data)
            if args.command == "prepare":
                result = store.prepare(request_id=args.request_id, stage=args.stage,
                                       route=args.route, expected_revision=args.expected_revision)
            elif args.command == "commit":
                result = store.commit(request_id=args.request_id, expected_revision=args.expected_revision)
            elif args.command == "revoke":
                result = store.revoke(args.release_id)
            else:
                content = store.download(args.release_id)
                if args.command == "evaluate":
                    from .mechanism import public_fixture_evaluation
                    result = public_fixture_evaluation(content)
                else:
                    # Exclusive creation also refuses symlinks and protects existing evidence.
                    with args.output.open("xb") as stream:
                        stream.write(content)
                    result = {"output": str(args.output.resolve()), "release_id": args.release_id,
                              "artifact_sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (ExportDenied, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"code": getattr(exc, "code", "invalid_request"), "detail": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
