from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HAS_EXPERIMENT_STACK = all(
    importlib.util.find_spec(name) is not None
    for name in ("numpy", "scipy", "sklearn", "torch", "xgboost")
)


@unittest.skipUnless(HAS_EXPERIMENT_STACK, "public privacy experiment dependencies unavailable")
class PublicPrivacyArtifactHashTests(unittest.TestCase):
    def test_sklearn_xgboost_wrapper_serializes_its_booster(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_public_privacy_audit_for_test",
            ROOT / "scripts" / "run_public_privacy_audit.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeBooster:
            def save_raw(self, *, raw_format: str) -> bytearray:
                self.raw_format = raw_format
                return bytearray(b"registered-booster")

        class FakeClassifier:
            def __init__(self) -> None:
                self.booster = FakeBooster()

            def get_booster(self) -> FakeBooster:
                return self.booster

        classifier = FakeClassifier()
        self.assertEqual(
            module.xgboost_booster_bytes(classifier),
            b"registered-booster",
        )
        self.assertEqual(classifier.booster.raw_format, "json")

    def test_low_level_booster_remains_supported(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_public_privacy_audit_booster_for_test",
            ROOT / "scripts" / "run_public_privacy_audit.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        class FakeBooster:
            def save_raw(self, *, raw_format: str) -> bytes:
                return f"booster:{raw_format}".encode("utf-8")

        self.assertEqual(
            module.xgboost_booster_bytes(FakeBooster()),
            b"booster:json",
        )


if __name__ == "__main__":
    unittest.main()
