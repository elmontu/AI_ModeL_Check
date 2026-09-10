"""Bounded scheduling sanity check; this is not a UC or implementation proof.

The two machines below independently express a small authorization kernel. The
real machine uses authenticated inbound and outbound queues. The ideal machine
defers request execution and output delivery with separate tickets. Inputs,
normalization and the harness are shared; authorization transition code is not.

Six scenarios each contain three distinct transport handles. Every interleaving
of each handle's Submit -> Receive -> Deliver chain is checked, including every
prefix (maximum nine actions). Grant copies may share one logical nonce. All
processed logical nonces cache their complete receipt, including denials. Time
is an explicit monotone logical Tick from a trusted clock identity, not physical
time or a machine-activation counter. A receipt records state at processing.

Nothing here models signatures, cryptographic adversaries, arbitrary messages,
arbitrary participants, corrupt parties, storage faults, the full MRA kernel,
the Python production implementation, or universal composition. The negative
variants are deliberate mutations used to exhibit scheduling counterexamples.
Importing this module does not execute checks or write files.
"""

from __future__ import annotations

import argparse
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
from typing import Any
import uuid


# (operation, logical nonce, attributed caller, parameter)
REQUESTS = {
    "g1": ("Grant", "grant-1", "client", None),
    "g1-copy": ("Grant", "grant-1", "client", None),
    "g2": ("Grant", "grant-2", "client", None),
    "revoke": ("Revoke", "revoke-1", "authority", None),
    "tick": ("Tick", "tick-1", "clock", 3),
}
SCENARIOS = (
    ("g1", "revoke", "tick"),
    ("g1", "g1-copy", "revoke"),
    ("g1", "g1-copy", "tick"),
    ("g1", "g2", "revoke"),
    ("g1", "g2", "tick"),
    ("g1", "g1-copy", "g2"),
)
DEADLINE = 3
Action = tuple[str, str]


class RealCoordinator:
    """Honest coordinator: direct imperative transitions on delivered packets."""

    def __init__(self) -> None:
        self.clock = 0
        self.status = "ACTIVE"
        self.budget = 1
        self.grants = 0
        self.revocations = 0
        self.used: dict[str, tuple[Any, ...]] = {}
        self.submitted: set[str] = set()
        self.inbound: dict[str, tuple[Any, ...]] = {}
        self.outbound: dict[str, tuple[Any, ...]] = {}
        self.returned: set[str] = set()
        self.trace: list[tuple[Any, ...]] = []

    def _on_authenticated_request(self, request: tuple[Any, ...]) -> tuple[Any, ...]:
        operation, nonce, caller, parameter = request
        if nonce in self.used:
            return self.used[nonce]
        if operation == "Grant":
            if caller != "client":
                outcome = "DENIED_CALLER"
            elif self.status != "ACTIVE":
                outcome = "DENIED_REVOKED"
            elif self.clock >= DEADLINE:
                outcome = "DENIED_EXPIRED"
            elif self.budget < 1:
                outcome = "DENIED_BUDGET"
            else:
                self.budget -= 1
                self.grants += 1
                outcome = "GRANTED"
        elif operation == "Revoke":
            if caller != "authority":
                outcome = "DENIED_CALLER"
            else:
                self.status = "REVOKED"
                self.revocations += 1
                outcome = "REVOKED"
        elif operation == "Tick":
            if caller != "clock":
                outcome = "DENIED_CALLER"
            else:
                self.clock = max(self.clock, parameter)
                outcome = "TICKED"
        else:
            outcome = "DENIED_OPERATION"
        receipt = (
            nonce, outcome, self.clock, self.status, self.budget,
            self.grants, self.revocations,
        )
        self.used[nonce] = receipt
        return receipt

    def act(self, action: Action) -> None:
        operation, handle = action
        if operation == "Submit":
            assert handle not in self.submitted
            self.submitted.add(handle)
            self.inbound[handle] = REQUESTS[handle]
            self.trace.append(("IN", handle, REQUESTS[handle]))
        elif operation == "Receive":
            request = self.inbound.pop(handle)
            receipt = self._on_authenticated_request(request)
            self.outbound[handle] = receipt
            self.trace.append(("OUT", handle, receipt))
        elif operation == "Deliver":
            receipt = self.outbound.pop(handle)
            self.returned.add(handle)
            self.trace.append(("RETURN", handle, receipt))
        else:
            raise ValueError(action)

    def snapshot(self) -> dict[str, Any]:
        return {
            "clock": self.clock, "status": self.status, "budget": self.budget,
            "grants": self.grants, "revocations": self.revocations,
            "nonce_receipts": sorted(self.used.items()),
            "submitted": sorted(self.submitted),
            "inbound": sorted(self.inbound.items()),
            "outbound": sorted(self.outbound.items()),
            "returned": sorted(self.returned), "public_trace": self.trace,
        }


class IdealDeferredService:
    """Ideal tickets with separately expressed policy and explicit mutations."""

    def __init__(self, mutation: str | None = None) -> None:
        self.state = {
            "time": 0, "active": True, "remaining": 1,
            "admissions": 0, "revocations": 0,
        }
        self.receipts: dict[str, tuple[Any, ...]] = {}
        self.input_tickets: dict[str, tuple[Any, ...]] = {}
        self.output_tickets: dict[str, tuple[Any, ...]] = {}
        self.known_tickets: set[str] = set()
        self.completed_tickets: set[str] = set()
        self.public_events: list[tuple[Any, ...]] = []
        self.mutation = mutation
        self.premature_results: dict[str, tuple[Any, ...]] = {}

    def _transition(self, request: tuple[Any, ...], *, bypass_cache: bool = False) -> tuple[Any, ...]:
        verb, token, identity, value = request
        prior = self.receipts.get(token)
        if prior is not None and not bypass_cache:
            if self.mutation == "reapply_duplicate_effect" and prior[1] == "GRANTED":
                # Deliberately wrong: a historical receipt replays its effect.
                self.state["admissions"] += 1
                self.state["remaining"] -= 1
            return prior

        if identity != {"Grant": "client", "Revoke": "authority", "Tick": "clock"}.get(verb):
            result = "DENIED_CALLER" if verb in {"Grant", "Revoke", "Tick"} else "DENIED_OPERATION"
        elif verb == "Tick":
            self.state["time"] = value if value > self.state["time"] else self.state["time"]
            result = "TICKED"
        elif verb == "Revoke":
            self.state.update(active=False, revocations=self.state["revocations"] + 1)
            result = "REVOKED"
        else:
            requirements = (
                (self.state["active"], "DENIED_REVOKED"),
                (self.state["time"] < DEADLINE, "DENIED_EXPIRED"),
                (self.state["remaining"] > 0, "DENIED_BUDGET"),
            )
            result = next((failure for valid, failure in requirements if not valid), "GRANTED")
            if result == "GRANTED":
                self.state.update(
                    admissions=self.state["admissions"] + 1,
                    remaining=self.state["remaining"] - 1,
                )
        answer = (
            token, result, self.state["time"],
            "ACTIVE" if self.state["active"] else "REVOKED",
            self.state["remaining"], self.state["admissions"],
            self.state["revocations"],
        )
        self.receipts[token] = answer
        return answer

    def act(self, action: Action) -> None:
        verb, ticket = action
        if verb == "Submit":
            assert ticket not in self.known_tickets
            self.known_tickets.add(ticket)
            self.input_tickets[ticket] = REQUESTS[ticket]
            self.public_events.append(("IN", ticket, REQUESTS[ticket]))
            if self.mutation == "apply_at_submission":
                self.premature_results[ticket] = self._transition(REQUESTS[ticket])
            return
        if verb == "Receive":
            request = self.input_tickets.pop(ticket)
            answer = (
                self.premature_results.pop(ticket)
                if self.mutation == "apply_at_submission"
                else self._transition(request)
            )
            self.output_tickets[ticket] = answer
            self.public_events.append(("OUT", ticket, answer))
            return
        if verb == "Deliver":
            answer = self.output_tickets.pop(ticket)
            if self.mutation == "reauthorize_at_receipt_delivery" and REQUESTS[ticket][0] == "Grant":
                # Deliberately wrong: treat output delivery as a fresh decision.
                answer = self._transition(REQUESTS[ticket], bypass_cache=True)
            self.completed_tickets.add(ticket)
            self.public_events.append(("RETURN", ticket, answer))
            return
        raise ValueError(action)

    def snapshot(self) -> dict[str, Any]:
        return {
            "clock": self.state["time"],
            "status": "ACTIVE" if self.state["active"] else "REVOKED",
            "budget": self.state["remaining"],
            "grants": self.state["admissions"],
            "revocations": self.state["revocations"],
            "nonce_receipts": sorted(self.receipts.items()),
            "submitted": sorted(self.known_tickets),
            "inbound": sorted(self.input_tickets.items()),
            "outbound": sorted(self.output_tickets.items()),
            "returned": sorted(self.completed_tickets),
            "public_trace": self.public_events,
        }


def enabled(scenario: tuple[str, ...], real: RealCoordinator) -> list[Action]:
    actions = []
    for handle in scenario:
        if handle not in real.submitted:
            actions.append(("Submit", handle))
        elif handle in real.inbound:
            actions.append(("Receive", handle))
        elif handle in real.outbound:
            actions.append(("Deliver", handle))
    return actions


def replay(actions: tuple[Action, ...], mutation: str | None = None) -> dict[str, Any]:
    real, ideal = RealCoordinator(), IdealDeferredService(mutation)
    first_state_difference = None
    first_trace_difference = None
    for index, action in enumerate(actions, start=1):
        real.act(action)
        ideal.act(action)
        if real.snapshot() != ideal.snapshot() and first_state_difference is None:
            first_state_difference = index
        if real.trace != ideal.public_events and first_trace_difference is None:
            first_trace_difference = index
    return {
        "mutation": mutation, "actions": actions,
        "first_state_difference_step": first_state_difference,
        "first_public_trace_difference_step": first_trace_difference,
        "real": real.snapshot(), "ideal": ideal.snapshot(),
    }


def check_scenario(scenario: tuple[str, ...]) -> dict[str, Any]:
    prefixes = 0
    complete_schedules = 0
    transitions = 0
    by_depth: dict[int, int] = {}

    def visit(real: RealCoordinator, ideal: IdealDeferredService, path: tuple[Action, ...]) -> None:
        nonlocal prefixes, complete_schedules, transitions
        prefixes += 1
        by_depth[len(path)] = by_depth.get(len(path), 0) + 1
        if real.snapshot() != ideal.snapshot():
            raise AssertionError(json.dumps(replay(path), sort_keys=True))
        if not 0 <= real.budget <= 1 or real.grants > 1:
            raise AssertionError("Positive machine violates its grant budget")
        if not real.clock >= 0 or real.status not in {"ACTIVE", "REVOKED"}:
            raise AssertionError("Invalid positive kernel state")
        actions = enabled(scenario, real)
        if not actions:
            complete_schedules += 1
        for action in actions:
            transitions += 1
            real_next, ideal_next = deepcopy(real), deepcopy(ideal)
            real_next.act(action)
            ideal_next.act(action)
            visit(real_next, ideal_next, path + (action,))

    visit(RealCoordinator(), IdealDeferredService(), ())
    # Independent combinatorial count: interleavings of three chains of length 3.
    expected_by_depth = {}
    for lengths in itertools.product(range(4), repeat=len(scenario)):
        depth = sum(lengths)
        from math import factorial
        ways = factorial(depth)
        for length in lengths:
            ways //= factorial(length)
        expected_by_depth[depth] = expected_by_depth.get(depth, 0) + ways
    assert by_depth == expected_by_depth, (by_depth, expected_by_depth)
    assert complete_schedules == 1680
    return {
        "transport_handles": scenario, "prefixes_including_empty": prefixes,
        "transitions": transitions, "complete_schedules": complete_schedules,
        "prefix_counts_by_depth": by_depth,
        "all_normalized_state_and_public_trace_comparisons_equal": True,
    }


def find_public_counterexample(mutation: str) -> dict[str, Any]:
    """BFS gives a shortest public-trace counterexample over declared scenarios."""
    visited_prefixes = 0
    queue = deque((scenario, (), RealCoordinator(), IdealDeferredService(mutation)) for scenario in SCENARIOS)
    while queue:
        scenario, path, real, ideal = queue.popleft()
        visited_prefixes += 1
        if real.trace != ideal.public_events:
            answer = replay(path, mutation)
            answer.update(scenario=scenario, searched_prefixes=visited_prefixes)
            return answer
        for action in enabled(scenario, real):
            next_real, next_ideal = deepcopy(real), deepcopy(ideal)
            next_real.act(action)
            next_ideal.act(action)
            queue.append((scenario, path + (action,), next_real, next_ideal))
    raise AssertionError(f"No public counterexample found for deliberate mutation {mutation}")


def run_checks() -> dict[str, Any]:
    positive = [check_scenario(scenario) for scenario in SCENARIOS]
    mutations = (
        "apply_at_submission", "reauthorize_at_receipt_delivery",
        "reapply_duplicate_effect",
    )
    counterexamples = [find_public_counterexample(mutation) for mutation in mutations]
    delayed = (
        ("Submit", "g1"), ("Receive", "g1"), ("Submit", "revoke"),
        ("Receive", "revoke"), ("Deliver", "g1"),
    )
    duplicate = (
        ("Submit", "g1"), ("Receive", "g1"), ("Submit", "g1-copy"),
        ("Receive", "g1-copy"), ("Submit", "revoke"), ("Receive", "revoke"),
    )
    expiry = (
        ("Submit", "g1"), ("Submit", "tick"), ("Receive", "tick"),
        ("Receive", "g1"), ("Deliver", "g1"),
    )
    witnesses = {
        "historical_grant_delivered_after_revocation": replay(delayed),
        "duplicate_logical_nonce_new_transport_handle": replay(duplicate),
        "tick_at_deadline_before_grant_is_processed": replay(expiry),
        "negative_delivery_reauthorization_after_revocation": replay(delayed, "reauthorize_at_receipt_delivery"),
        "negative_duplicate_effect_visible_in_later_receipt": replay(duplicate, "reapply_duplicate_effect"),
        "negative_apply_at_submission_ignores_later_deadline": replay(expiry, "apply_at_submission"),
    }
    for name, witness in witnesses.items():
        if name.startswith("negative_"):
            assert witness["first_public_trace_difference_step"] is not None
        else:
            assert witness["first_state_difference_step"] is None
    assert witnesses["historical_grant_delivered_after_revocation"]["real"]["public_trace"][-1][2][1] == "GRANTED"
    assert witnesses["historical_grant_delivered_after_revocation"]["real"]["status"] == "REVOKED"
    assert witnesses["tick_at_deadline_before_grant_is_processed"]["real"]["public_trace"][-1][2][1] == "DENIED_EXPIRED"
    return {
        "status": "PASS",
        "scope": "Bounded scheduling skeleton only; not a UC proof or full-kernel/production verification.",
        "model": {
            "initial_status": "ACTIVE", "initial_clock": 0, "strict_deadline": DEADLINE,
            "initial_budget": 1, "request_catalog": REQUESTS,
            "nonce_rule": "Cache every processed request's full receipt; duplicate grant transport handles carry identical request bytes.",
            "communication": "Full public inbound/outbound contents; separate input and output delivery tickets; arbitrarily delayed/reordered delivery within the bound.",
            "time": "Explicit trusted monotone logical Tick, not physical time or activation count.",
            "observation": "IN/OUT/RETURN event trace, including complete receipt values; compare all normalized kernel, nonce, transport and trace state after every prefix.",
            "shared_code": "Request/action types and catalog, snapshots' vocabulary, action generation, enumeration and comparison harness; kernel transitions are independently expressed.",
            "limitations": [
                "Six fixed scenarios, each with three transport handles and at most nine actions.",
                "No arbitrary request bytes, nonce/payload conflicts, corrupt identities or dynamic participants.",
                "No crypto, machine-runtime wiring, UC theorem, implementation refinement, storage crash, physical time, full lifecycle policy, or model training.",
                "The two machines and harness were written by the same AI agent; independent expression does not mean an independent external validation.",
            ],
        },
        "positive_scenarios": positive,
        "totals": {
            "scenario_count": len(positive),
            "scenario_prefix_comparisons": sum(item["prefixes_including_empty"] for item in positive),
            "scenario_transitions": sum(item["transitions"] for item in positive),
            "complete_schedules": sum(item["complete_schedules"] for item in positive),
            "max_actions": 9, "negative_mutations_detected": len(counterexamples),
            "counts_are_scenario_indexed_not_globally_unique_traces": True,
        },
        "negative_counterexamples": counterexamples,
        "named_witnesses": witnesses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=Path("output/uc-scheduling-20260909"))
    args = parser.parse_args()
    results = run_checks()
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    destination = args.output_root.resolve() / run_id
    destination.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).resolve()
    results.update(
        created_utc=now.isoformat(), script=str(script),
        script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
        python_version=sys.version, platform=platform.platform(),
    )
    output = destination / "results.json"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(results, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": results["status"], "results": str(output), **results["totals"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
