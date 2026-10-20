
"""CLI separates runtime freeze, qualification, one execution and verification."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from . import store

def _runtime(parser):
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--runtime-sha256", required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--qualification-sha256", required=True)

def _completed(parser):
    _runtime(parser)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--completion-sha256", required=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 7C frozen-plan public retrospective evaluation; no release authority.")
    parser.add_argument("--repository", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="Freeze implemented runtime bytes before actual outcome derivation")
    freeze.add_argument("--output", type=Path, required=True)
    qualify = commands.add_parser("qualify", help="Independent synthetic numerical qualification before execution")
    qualify.add_argument("--runtime", type=Path, required=True)
    qualify.add_argument("--runtime-sha256", required=True)
    qualify.add_argument("--output", type=Path, required=True)
    execution = commands.add_parser("execute", help="Reserve and execute exactly once; incomplete attempts cannot be retried")
    _runtime(execution)
    for name in ("validate", "replay"):
        command = commands.add_parser(name, help="Verify externally pinned completion using full deterministic captured-byte replay")
        _completed(command)
    commands.add_parser("status", help="Show reservations and completion presence; makes no numerical claim")
    serve = commands.add_parser("serve", help="Read-only loopback demonstration; cold completed state is replayed before serving")
    serve.add_argument("--port", type=int, default=8769)
    serve.add_argument("--runtime", type=Path)
    serve.add_argument("--runtime-sha256")
    serve.add_argument("--qualification", type=Path)
    serve.add_argument("--qualification-sha256")
    serve.add_argument("--execution", type=Path)
    serve.add_argument("--completion-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            result = store.freeze_manifest(args.repository, args.output)
        elif args.command == "qualify":
            store.verify_runtime(args.repository, args.runtime, args.runtime_sha256)
            from .verifier import qualify_synthetic
            result = qualify_synthetic(runtime_sha256=args.runtime_sha256)
            data = store.canonical(result)
            store.write_once(args.output, data)
            result = {"qualification_sha256": store.sha(data), "qualification": result}
        elif args.command == "execute":
            result = store.execute(args.repository, args.runtime, args.runtime_sha256,
                                   args.qualification, args.qualification_sha256,
                                   progress=lambda value: print(store.canonical(value).decode(), file=sys.stderr, flush=True))
        elif args.command in ("validate", "replay"):
            result = store.open_completed(args.repository, args.execution, args.completion_sha256,
                                         args.runtime, args.runtime_sha256, args.qualification, args.qualification_sha256,
                                         replay=True, progress=lambda value: print(store.canonical(value).decode(), file=sys.stderr, flush=True))
        elif args.command == "status":
            result = store.status(args.repository)
        else:
            from .web import create_app
            import uvicorn
            if not 1 <= args.port <= 65535:
                raise store.ExecutionError("Invalid loopback port")
            app = create_app(args.repository, runtime_path=args.runtime, runtime_sha256=args.runtime_sha256,
                             qualification_path=args.qualification, qualification_sha256=args.qualification_sha256,
                             execution_dir=args.execution, completion_sha256=args.completion_sha256)
            uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
            return 0
        print(store.canonical(result).decode(), end="")
        return 0
    except (store.ExecutionError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, "Phase 7C refused: " + str(exc) + "\n")

if __name__ == "__main__":
    main()

