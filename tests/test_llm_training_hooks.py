from __future__ import annotations

import inspect
import json
import math
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from llm_training_hooks import (  # noqa: E402
    AggregateTrainingHookCollector,
    EventCapError,
    EventIntegrityError,
    HookConfigurationError,
    HookCoverageError,
    NonFiniteTelemetryError,
    STAT_KEYS,
    TorchUnavailableError,
    _event_digest,
)


try:
    import torch
    from torch import nn
except (ImportError, OSError):  # Keep the core dependency tier importable.
    TORCH_AVAILABLE = False
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
else:
    TORCH_AVAILABLE = True


def _contains_tensor(value: Any) -> bool:
    if torch is not None and torch.is_tensor(value):
        return True
    if isinstance(value, dict):
        return any(_contains_tensor(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_tensor(item) for item in value)
    return False


class OptionalDependencyTests(unittest.TestCase):
    def test_module_imports_without_mandatory_torch_dependency(self) -> None:
        if TORCH_AVAILABLE:
            self.assertTrue(callable(AggregateTrainingHookCollector))
        else:
            with self.assertRaises(TorchUnavailableError):
                AggregateTrainingHookCollector(object(), ["layer"])

    def test_event_digest_is_canonical_and_strict_json(self) -> None:
        left = {
            "sequence": 0,
            "previous_sha256": "0" * 64,
            "stats": {"elements": 2, "rms": 1.5},
        }
        right = {
            "stats": {"rms": 1.5, "elements": 2},
            "previous_sha256": "0" * 64,
            "sequence": 0,
        }
        self.assertEqual(_event_digest(left), _event_digest(right))
        with self.assertRaisesRegex(EventIntegrityError, "strict JSON"):
            _event_digest({"value": float("nan")})

    def test_worker_facing_signature_is_available_without_importing_torch(self) -> None:
        constructor = inspect.signature(AggregateTrainingHookCollector)
        step = inspect.signature(AggregateTrainingHookCollector.step)
        finalize = inspect.signature(AggregateTrainingHookCollector.finalize)
        for name in ("module_names", "max_events", "fail_on_nonfinite"):
            self.assertIn(name, constructor.parameters)
        for name in (
            "loss",
            "input_tokens",
            "target_tokens",
            "duration_seconds",
            "gpu_memory",
        ):
            self.assertIn(name, step.parameters)
        self.assertIn("expected_steps", finalize.parameters)


@unittest.skipUnless(TORCH_AVAILABLE, "optional PyTorch dependency is unavailable")
class AggregateTrainingHookCollectorTests(unittest.TestCase):
    class TinyModel(nn.Module if nn is not None else object):
        def __init__(self) -> None:
            super().__init__()
            self.fc1 = nn.Linear(4, 3)
            self.fc2 = nn.Linear(3, 2)

        def forward(self, inputs):
            return self.fc2(torch.tanh(self.fc1(inputs)))

    def setUp(self) -> None:
        torch.manual_seed(7)
        self.model = self.TinyModel()

    def _backward_once(self):
        inputs = torch.arange(8, dtype=torch.float32).reshape(2, 4) / 8
        targets = torch.zeros((2, 2), dtype=torch.float32)
        output = self.model(inputs)
        loss = torch.nn.functional.mse_loss(output, targets)
        loss.backward()
        return inputs, loss

    def test_success_is_aggregate_only_hash_chained_and_cleans_up(self) -> None:
        before = {
            "fc1_forward": len(self.model.fc1._forward_hooks),
            "fc1_backward": len(self.model.fc1._backward_hooks),
            "fc2_forward": len(self.model.fc2._forward_hooks),
            "fc2_backward": len(self.model.fc2._backward_hooks),
        }
        collector = AggregateTrainingHookCollector(
            self.model,
            ["fc1", "fc2"],
            expected_steps=2,
            event_cap=10,
            context_sha256="a" * 64,
        )
        with collector:
            for _ in range(2):
                self.model.zero_grad(set_to_none=True)
                inputs, loss = self._backward_once()
                collector.step(loss, tokens=int(inputs.numel()), duration_seconds=0.25)

        report = collector.finalize()
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["aggregate_only"])
        self.assertFalse(report["raw_tensors_retained"])
        self.assertFalse(report["raw_text_retained"])
        self.assertFalse(report["raw_token_arrays_retained"])
        self.assertEqual(report["event_count"], 10)
        self.assertTrue(report["context_bound"])
        self.assertEqual(report["event_chain_genesis_sha256"], "a" * 64)
        self.assertEqual(report["events"][0]["previous_sha256"], "a" * 64)
        self.assertEqual(report["coverage"]["required_forward_events"], 4)
        self.assertEqual(report["coverage"]["observed_backward_events"], 4)
        self.assertTrue(report["coverage"]["handles_removed"])
        self.assertFalse(_contains_tensor(report))
        json.dumps(report, allow_nan=False)

        hook_events = [
            event for event in report["events"] if event["event_type"] != "step"
        ]
        for event in hook_events:
            self.assertEqual(tuple(event["stats"]), STAT_KEYS)
            self.assertGreater(event["stats"]["elements"], 0)
            self.assertEqual(event["stats"]["nonfinite"], 0)
            self.assertTrue(math.isfinite(event["stats"]["rms"]))
            self.assertNotIn("tensor", event)
            self.assertNotIn("input", event)
            self.assertNotIn("output", event)

        step_events = [
            event for event in report["events"] if event["event_type"] == "step"
        ]
        self.assertEqual(len(step_events), 2)
        self.assertEqual(step_events[0]["tokens"], 8)
        self.assertEqual(step_events[0]["duration_seconds"], 0.25)
        self.assertEqual(tuple(step_events[0]["parameter_gradients"]), STAT_KEYS)
        self.assertTrue(step_events[0]["parameter_gradient_coverage"]["complete"])
        self.assertEqual(
            step_events[0]["parameter_gradient_coverage"]["missing_trainable_parameter_gradient_tensors"],
            0,
        )
        self.assertIn("allocated_bytes", step_events[0]["gpu_memory"])

        after = {
            "fc1_forward": len(self.model.fc1._forward_hooks),
            "fc1_backward": len(self.model.fc1._backward_hooks),
            "fc2_forward": len(self.model.fc2._forward_hooks),
            "fc2_backward": len(self.model.fc2._backward_hooks),
        }
        self.assertEqual(after, before)

    def test_exact_allowlist_rejects_missing_module_without_partial_hooks(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "does.not.exist"], expected_steps=1
        )
        with self.assertRaisesRegex(HookConfigurationError, "unknown exact names"):
            collector.__enter__()
        self.assertEqual(len(self.model.fc1._forward_hooks), 0)
        self.assertEqual(len(self.model.fc1._backward_hooks), 0)

    def test_step_fails_before_optimizer_on_missing_hook_coverage(self) -> None:
        class Branched(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.used = nn.Linear(2, 2)
                self.unused = nn.Linear(2, 2)

            def forward(self, value):
                return self.used(value)

        model = Branched()
        collector = AggregateTrainingHookCollector(
            model, ["used", "unused"], expected_steps=1
        )
        with self.assertRaisesRegex(HookCoverageError, "unused"):
            with collector:
                loss = model(torch.ones((1, 2))).square().mean()
                loss.backward()
                collector.step(loss, tokens=2)
        self.assertEqual(len(model.used._forward_hooks), 0)
        self.assertEqual(len(model.used._backward_hooks), 0)

    def test_step_fails_when_a_trainable_parameter_has_no_gradient(self) -> None:
        class PartiallyDetached(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.used = nn.Linear(2, 2)
                self.unused_trainable = nn.Parameter(torch.ones(3))

            def forward(self, value):
                return self.used(value)

        model = PartiallyDetached()
        collector = AggregateTrainingHookCollector(model, ["used"], expected_steps=1)
        with self.assertRaisesRegex(HookCoverageError, "not every trainable parameter"):
            with collector:
                loss = model(torch.ones((1, 2))).square().mean()
                loss.backward()
                collector.step(loss, tokens=2)
        self.assertTrue(collector.handles_removed)
        step = collector.events[-1]
        self.assertFalse(step["parameter_gradient_coverage"]["complete"])
        self.assertEqual(
            step["parameter_gradient_coverage"]["missing_trainable_parameter_gradient_tensors"],
            1,
        )

    def test_nonfinite_forward_fails_and_context_removes_hooks(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1"], expected_steps=1
        )
        with self.assertRaises(NonFiniteTelemetryError):
            with collector:
                self.model(torch.full((1, 4), float("nan")))
        self.assertEqual(len(self.model.fc1._forward_hooks), 0)
        self.assertEqual(len(self.model.fc1._backward_hooks), 0)

    def test_nonfinite_loss_is_recorded_as_null_then_fails(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "fc2"], expected_steps=1
        )
        with self.assertRaisesRegex(NonFiniteTelemetryError, "loss"):
            with collector:
                inputs, finite_loss = self._backward_once()
                collector.step(float("nan"), tokens=int(inputs.numel()))
        step = collector.events[-1]
        self.assertEqual(step["event_type"], "step")
        self.assertIsNone(step["loss"])
        self.assertTrue(step["loss_nonfinite"])

    def test_event_cap_fails_before_unbounded_append(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "fc2"], event_cap=4
        )
        with self.assertRaises(EventCapError):
            with collector:
                inputs, loss = self._backward_once()
                collector.step(loss, tokens=int(inputs.numel()))
        self.assertEqual(len(collector.events), 4)
        self.assertEqual(len(self.model.fc1._forward_hooks), 0)
        self.assertEqual(len(self.model.fc1._backward_hooks), 0)

    def test_expected_steps_preflights_event_capacity(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1"], expected_steps=2, event_cap=5
        )
        with self.assertRaisesRegex(EventCapError, "need 6"):
            collector.__enter__()
        self.assertEqual(len(self.model.fc1._forward_hooks), 0)
        self.assertEqual(len(self.model.fc1._backward_hooks), 0)

    def test_finalize_detects_event_tampering(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "fc2"], expected_steps=1
        )
        collector.__enter__()
        inputs, loss = self._backward_once()
        collector.step(loss, tokens=int(inputs.numel()))
        collector.close()
        collector._events[0]["stats"]["zero"] += 1
        with self.assertRaisesRegex(EventIntegrityError, "digest mismatch"):
            collector.finalize()
        self.assertTrue(collector.handles_removed)

    def test_expected_step_shortfall_fails_after_cleanup(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "fc2"], expected_steps=2
        )
        with collector:
            inputs, loss = self._backward_once()
            collector.step(loss, tokens=int(inputs.numel()))
        with self.assertRaisesRegex(HookCoverageError, "successful step count"):
            collector.finalize()
        self.assertTrue(collector.handles_removed)

    def test_body_exception_cannot_finalize_as_a_pass(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model, ["fc1", "fc2"], expected_steps=1
        )
        with self.assertRaisesRegex(RuntimeError, "training aborted"):
            with collector:
                inputs, loss = self._backward_once()
                collector.step(loss, tokens=int(inputs.numel()))
                raise RuntimeError("training aborted")
        with self.assertRaisesRegex(HookCoverageError, "exited with an exception"):
            collector.finalize()
        self.assertTrue(collector.handles_removed)

    def test_runner_compatible_scalar_interface(self) -> None:
        collector = AggregateTrainingHookCollector(
            self.model,
            module_names=("fc1", "fc2"),
            max_events=5,
            fail_on_nonfinite=True,
        )
        with collector:
            inputs, loss = self._backward_once()
            collector.step(
                step=0,
                epoch=0,
                batch_index=0,
                loss=float(loss.detach()),
                model=self.model,
                learning_rate=5e-5,
                input_tokens=int(inputs.numel()),
                target_tokens=4,
                truncated_records=0,
                batch_manifest_sha256="a" * 64,
                duration_seconds=0.1,
                gpu_memory={
                    "allocated_bytes": 0,
                    "reserved_bytes": 0,
                    "peak_allocated_bytes": 0,
                },
            )
        collector.remove()
        report = collector.finalize(expected_steps=1)
        self.assertEqual(report["coverage_status"], "complete")
        self.assertEqual(report["observed_forward_events"], 2)
        self.assertEqual(report["observed_backward_events"], 2)
        self.assertEqual(report["nonfinite_elements"], 0)
        step_event = report["events"][-1]
        self.assertEqual(step_event["target_tokens"], 4)
        self.assertEqual(step_event["batch_manifest_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
