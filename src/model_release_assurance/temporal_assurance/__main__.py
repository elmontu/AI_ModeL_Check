"""Trusted local operator CLI; the experiment importer initializes registries."""
from __future__ import annotations
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from .store import AssuranceStore, AssuranceError


def existing(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("An existing initialized ledger file is required")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        config = dict(db.execute("SELECT key,value FROM meta"))
    return AssuranceStore(path, budget_micros=int(config["budget_micros"]), scope_digest=config["scope_digest"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Operate an initialized local temporal-assurance ledger; no arbitrary model/DP-certificate import.")
    parser.add_argument("--db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--full-ledger", action="store_true", help="show trusted audit unit-level charges; output may be large")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--request", required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--authority", required=True)
    prepare.add_argument("--expected-revision", type=int, required=True)
    commit = sub.add_parser("commit")
    commit.add_argument("--request", required=True)
    download = sub.add_parser("download")
    download.add_argument("--request", required=True)
    download.add_argument("--authority", required=True)
    download.add_argument("--output", type=Path, required=True)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--request", required=True)
    authority = sub.add_parser("revoke-authority")
    authority.add_argument("--authority", required=True)
    evidence = sub.add_parser("invalidate-evidence")
    evidence.add_argument("--digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = existing(args.db)
        now = None  # The broker samples its trusted clock inside the transaction.
        if args.command == "status":
            ledger = store.ledger()
            result = ledger if args.full_ledger else {
                "revision": ledger["revision"], "committed_releases": ledger["committed_releases"],
                "budget_epsilon": ledger["budget_micros"] / 1_000_000,
                "maximum_spent_epsilon": max(ledger["spent_micros"].values(), default=0) / 1_000_000,
                "charged_units": len(ledger["spent_micros"]), "mechanism_unit_charges": len(ledger["charges"]),
                "scope_digest": ledger["scope_digest"]}
        elif args.command == "prepare":
            result = store.prepare(args.request, args.model, expected_revision=args.expected_revision, authority_id=args.authority, now=now)
        elif args.command == "commit":
            result = store.commit(args.request, now=now)
        elif args.command == "download":
            # Exclusive creation prevents overwrite; a failed gate leaves no bytes.
            if args.output.exists():
                raise FileExistsError("Refusing to overwrite recipient output")
            content = store.download(args.request, authority_id=args.authority, now=now)
            with args.output.open("xb") as handle:
                handle.write(content)
            result = {"status": "delivered", "bytes": len(content), "path": str(args.output)}
        elif args.command == "revoke":
            store.revoke_release(args.request)
            result = {"status": "future_delivery_revoked", "past_disclosure_and_budget_retained": True}
        elif args.command == "revoke-authority":
            store.revoke_authority(args.authority)
            result = {"status": "authority_revoked"}
        else:
            store.invalidate_evidence(args.digest)
            result = {"status": "evidence_invalidated"}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (AssuranceError, OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"status": "blocked", "reason": getattr(error, "code", type(error).__name__), "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
