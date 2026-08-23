from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

from model_release_assurance.release_protocol import (
    ReleaseProtocolEventType,
    ReleaseProtocolRole,
    ReleaseProtocolState,
    _EVENT_ROLES,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "formal" / "protocol-correspondence-v1.json"
PROTOCOL = ROOT / "formal" / "lean" / "MRAP" / "Protocol.lean"


def _lean_constructors(source: str, inductive: str) -> set[str]:
    match = re.search(
        rf"inductive {re.escape(inductive)} where(?P<body>.*?)\n  deriving",
        source,
        re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"Lean inductive {inductive} was not found")
    return set(re.findall(r"^  \| ([A-Za-z][A-Za-z0-9]*)", match.group("body"), re.MULTILINE))


class FormalCorrespondenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.lean = PROTOCOL.read_text(encoding="utf-8")

    def test_every_python_role_and_state_has_a_lean_name(self) -> None:
        self.assertEqual(
            set(self.manifest["roles"]),
            {role.value for role in ReleaseProtocolRole},
        )
        self.assertEqual(
            set(self.manifest["states"]),
            {state.value for state in ReleaseProtocolState},
        )
        self.assertEqual(
            set(self.manifest["roles"].values()),
            _lean_constructors(self.lean, "Role"),
        )
        self.assertEqual(
            set(self.manifest["states"].values()),
            _lean_constructors(self.lean, "Phase"),
        )

    def test_every_python_event_and_role_permission_is_guarded(self) -> None:
        events = self.manifest["events"]
        self.assertEqual(set(events), {event.value for event in ReleaseProtocolEventType})
        for event in ReleaseProtocolEventType:
            expected_roles = sorted(role.value for role in _EVENT_ROLES[event])
            self.assertEqual(events[event.value]["python_roles"], expected_roles)

    def test_every_mapped_action_exists_in_lean(self) -> None:
        lean_actions = _lean_constructors(self.lean, "Action")
        mapped_actions = {
            action
            for event in self.manifest["events"].values()
            for action in event["lean_actions"]
        }
        mapped_actions.update(self.manifest["lean_environment_actions"])
        self.assertEqual(mapped_actions, lean_actions)

    def test_manifest_refuses_to_claim_refinement(self) -> None:
        self.assertIn("not a semantic refinement proof", self.manifest["claim"])


if __name__ == "__main__":
    unittest.main()
