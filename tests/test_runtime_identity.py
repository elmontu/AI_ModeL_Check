from __future__ import annotations

import unittest

from model_release_assurance.runtime_identity import (
    current_runtime_identity,
    package_source_sha256,
)


class RuntimeIdentityTests(unittest.TestCase):
    def test_package_source_digest_and_profile_are_deterministic(self) -> None:
        profile = {
            "arithmetic": "python_binary64",
            "decision_boundary": "reference_only",
        }
        first = current_runtime_identity("test_component", "1.0", profile)
        second = current_runtime_identity("test_component", "1.0", profile)

        self.assertEqual(first, second)
        self.assertEqual(first.package_source_sha256, package_source_sha256())
        self.assertRegex(first.package_source_sha256, r"^[0-9a-f]{64}$")
        self.assertIn("pydantic", first.dependency_versions)

    def test_algorithm_profile_digest_changes_with_semantics(self) -> None:
        left = current_runtime_identity(
            "test_component",
            "1.0",
            {"comparison": "strict"},
        )
        right = current_runtime_identity(
            "test_component",
            "1.0",
            {"comparison": "outward_rounded"},
        )

        self.assertNotEqual(
            left.algorithm_profile_sha256,
            right.algorithm_profile_sha256,
        )


if __name__ == "__main__":
    unittest.main()
