"""Copy validated PRD15 history while the authoritative write lock is held.

This is a trusted internal bridge, never a caller-supplied snapshot authority.
It does not alter the prior registry implementation or issue release permission.
"""
from __future__ import annotations

from ..production_registry import contracts as registry_contracts
from .contracts import FLAGS, validate_history


class RegistryHistoryReader:
    def __init__(self, registry_service):
        self._service = registry_service
        self._store = registry_service._store
        self._broker = registry_service._broker

    def with_snapshot(self, *, guard, callback):
        """Lock order: current identity → registry DB → witness DB.

        The callback is trusted server code. It must not call registry commit
        while this transaction is held. Final PRD15 validation/authorization
        still runs after the callback, before the returned result is accepted.
        """
        if not callable(callback) or not callable(guard):
            raise ValueError("Trusted current guard and callback are required")
        with self._store._transaction(guard, self._broker) as (connection, state, now, _):
            rows = connection.execute("SELECT * FROM events ORDER BY sequence LIMIT 2049").fetchall()
            if len(rows) != state["count"] or len(rows) > 2048:
                raise ValueError("Bounded complete registry history is required")
            events = [{"event_sha256": row["event_sha256"],
                       "event": registry_contracts.strict_json(row["event_json"].encode("ascii"))}
                      for row in rows]
            snapshot = validate_history({"schema": "mra-fixture-registry-history-snapshot/v1",
                "store_id": self._store.store_id, "schema_version": state["version"],
                "broker_epoch": state["epoch"], "broker_id": state["broker_id"],
                "event_sequence": state["count"], "event_head_sha256": state["head"],
                "observed_at": now, "events": events, **FLAGS})
            guard()  # Complete copying/replay can consume the token lifetime.
            result = callback(snapshot)
        return result

    def snapshot(self, *, guard):
        return self.with_snapshot(guard=guard, callback=lambda history: history)
