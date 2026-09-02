#!/usr/bin/env python3
"""Bounded, aggregate-only PyTorch telemetry for LLM training smoke tests.

The collector intentionally retains no activations, gradients, input text, token
IDs, or other sample-level material.  Hook values are reduced immediately to
scalar counts and norms and written to a bounded, hash-chained event ledger.

Call :meth:`AggregateTrainingHookCollector.step` after ``loss.backward()`` and
before ``optimizer.step()``.  A successful step requires exactly one forward
and one full-backward event from every explicitly allowlisted module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Callable

try:  # PyTorch is an optional experiment dependency for this repository.
    import torch
except (ImportError, OSError):  # pragma: no cover - dependency-minimal CI.
    torch = None  # type: ignore[assignment]


SCHEMA_VERSION = "1.0"
GENESIS_SHA256 = "0" * 64
STAT_KEYS = (
    "count",
    "elements",
    "nonfinite",
    "zero",
    "max_abs",
    "sum_squares",
    "rms",
    "finite_fraction",
    "l2_norm",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class TrainingHookError(RuntimeError):
    """Base class for fail-closed training telemetry errors."""


class TorchUnavailableError(TrainingHookError):
    """Raised when the optional PyTorch dependency is unavailable."""


class HookConfigurationError(TrainingHookError):
    """Raised for an invalid model, allowlist, or collector bound."""


class HookStateError(TrainingHookError):
    """Raised when collector methods are called out of order."""


class HookCoverageError(TrainingHookError):
    """Raised when an allowlisted module is not observed exactly as required."""


class NonFiniteTelemetryError(TrainingHookError):
    """Raised when loss, activations, or gradients contain a non-finite value."""


class EventCapError(TrainingHookError):
    """Raised before a telemetry event could exceed the configured cap."""


class HookCleanupError(TrainingHookError):
    """Raised when one or more registered hook handles cannot be removed."""


class EventIntegrityError(TrainingHookError):
    """Raised when the bounded event hash chain does not replay exactly."""


def _require_torch() -> Any:
    if torch is None:
        raise TorchUnavailableError(
            "PyTorch is required to collect training hooks; install the optional "
            "llm-experiments dependency"
        )
    return torch


def _strict_positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise HookConfigurationError(f"{name} must be an integer >= 1")
    return value


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HookConfigurationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise NonFiniteTelemetryError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise HookConfigurationError(f"{name} must be >= {minimum}")
    return result


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:  # Defensive: only scalars enter events.
        raise EventIntegrityError("telemetry event is not strict JSON") from exc
    return encoded.encode("utf-8")


def _event_digest(event_without_digest: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(event_without_digest)).hexdigest()


def _iter_tensors(value: Any, seen: set[int] | None = None) -> Iterator[Any]:
    """Yield tensor leaves without retaining their surrounding object graph."""

    runtime = _require_torch()
    if runtime.is_tensor(value):
        yield value
        return
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return

    if seen is None:
        seen = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for child in value.values():
            yield from _iter_tensors(child, seen)
        return
    if isinstance(value, (tuple, list)):
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        for child in value:
            yield from _iter_tensors(child, seen)


@dataclass
class _Aggregate:
    count: int = 0
    elements: int = 0
    nonfinite: int = 0
    zero: int = 0
    max_abs: float = 0.0
    sum_squares: float = 0.0

    def add_tensor(self, tensor: Any) -> None:
        runtime = _require_torch()
        detached = tensor.detach()
        if detached.layout != runtime.strided:
            detached = detached.to_dense()

        self.count += 1
        element_count = int(detached.numel())
        self.elements += element_count
        if element_count == 0:
            return

        if detached.is_complex():
            magnitudes = detached.abs().to(dtype=runtime.float64)
        else:
            magnitudes = detached.to(dtype=runtime.float64).abs()

        finite_mask = runtime.isfinite(magnitudes)
        nonfinite = int((~finite_mask).sum().item())
        self.nonfinite += nonfinite
        self.zero += int(((magnitudes == 0) & finite_mask).sum().item())

        finite_count = element_count - nonfinite
        if finite_count:
            safe_magnitudes = magnitudes.masked_fill(~finite_mask, 0.0)
            tensor_max = float(safe_magnitudes.max().item())
            tensor_sum_squares = float(safe_magnitudes.square().sum().item())
            if not math.isfinite(tensor_max) or not math.isfinite(tensor_sum_squares):
                raise NonFiniteTelemetryError(
                    "a finite tensor produced a non-finite aggregate"
                )
            self.max_abs = max(self.max_abs, tensor_max)
            self.sum_squares += tensor_sum_squares
            if not math.isfinite(self.sum_squares):
                raise NonFiniteTelemetryError("aggregate sum_squares overflowed")

    def as_dict(self) -> dict[str, int | float | None]:
        if self.elements == 0:
            rms: float | None = 0.0
            finite_fraction: float | None = None
        elif self.nonfinite:
            rms = None
            finite_fraction = (self.elements - self.nonfinite) / self.elements
        else:
            rms = math.sqrt(self.sum_squares / self.elements)
            finite_fraction = 1.0
        l2_norm = None if self.nonfinite else math.sqrt(self.sum_squares)
        return {
            "count": self.count,
            "elements": self.elements,
            "nonfinite": self.nonfinite,
            "zero": self.zero,
            "max_abs": self.max_abs,
            "sum_squares": self.sum_squares,
            "rms": rms,
            "finite_fraction": finite_fraction,
            "l2_norm": l2_norm,
        }


def aggregate_tensor_tree(value: Any) -> dict[str, int | float | None]:
    """Reduce all tensor leaves in ``value`` to aggregate scalar statistics."""

    aggregate = _Aggregate()
    for tensor in _iter_tensors(value):
        aggregate.add_tensor(tensor)
    return aggregate.as_dict()


class AggregateTrainingHookCollector:
    """Collect bounded aggregate statistics from exact PyTorch module names.

    Parameters
    ----------
    model:
        The ``torch.nn.Module`` being trained.
    module_allowlist:
        Exact names from ``model.named_modules()``.  Globs, prefixes, and
        implicit descendants are not supported. ``module_names`` is an alias
        used by the end-to-end worker.
    expected_steps:
        Optional exact number of calls to :meth:`step`.  If omitted, final
        coverage is checked against the observed number of successful steps.
    event_cap:
        Maximum retained forward, backward, and step events combined.
        ``max_events`` is an equivalent alias.
    context_sha256:
        Optional registered experiment-context digest used as the event-chain
        genesis. Worker reports must retain the corresponding context object.
    clock:
        Monotonic clock injectable for deterministic tests.
    """

    def __init__(
        self,
        model: Any,
        module_allowlist: Iterable[str] | None = None,
        *,
        module_names: Iterable[str] | None = None,
        expected_steps: int | None = None,
        event_cap: int | None = None,
        max_events: int | None = None,
        fail_on_nonfinite: bool = True,
        context_sha256: str | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        runtime = _require_torch()
        if not isinstance(model, runtime.nn.Module):
            raise HookConfigurationError("model must be a torch.nn.Module")
        if module_allowlist is not None and module_names is not None:
            raise HookConfigurationError(
                "provide module_allowlist or module_names, not both"
            )
        if module_allowlist is None:
            module_allowlist = module_names
        if module_allowlist is None:
            raise HookConfigurationError("an exact module allowlist is required")
        if isinstance(module_allowlist, (str, bytes)):
            raise HookConfigurationError(
                "module_allowlist must be an iterable of exact names"
            )
        names = tuple(module_allowlist)
        if not names:
            raise HookConfigurationError("module_allowlist must not be empty")
        if any(not isinstance(name, str) or not name for name in names):
            raise HookConfigurationError(
                "module_allowlist entries must be non-empty strings"
            )
        if len(names) != len(set(names)):
            raise HookConfigurationError("module_allowlist must not contain duplicates")
        if expected_steps is not None:
            expected_steps = _strict_positive_integer(expected_steps, "expected_steps")
        if event_cap is not None and max_events is not None:
            raise HookConfigurationError("provide event_cap or max_events, not both")
        if event_cap is None:
            event_cap = max_events if max_events is not None else 10_000
        self._event_cap = _strict_positive_integer(event_cap, "event_cap")
        if fail_on_nonfinite is not True:
            raise HookConfigurationError("fail_on_nonfinite must remain true")
        if context_sha256 is not None and (
            not isinstance(context_sha256, str)
            or SHA256_PATTERN.fullmatch(context_sha256) is None
        ):
            raise HookConfigurationError(
                "context_sha256 must be a lowercase SHA-256 digest"
            )
        if not callable(clock):
            raise HookConfigurationError("clock must be callable")

        self._model = model
        self._module_names = names
        self._expected_steps = expected_steps
        self._clock = clock
        self._lock = threading.RLock()

        self._events: list[dict[str, Any]] = []
        self._event_chain_genesis = context_sha256 or GENESIS_SHA256
        self._event_chain_head = self._event_chain_genesis
        self._phase_counts: dict[tuple[int, str, str], int] = {}
        self._handles: list[Any] = []
        self._installed_handle_count = 0
        self._removed_handle_count = 0
        self._cleanup_failures: list[str] = []
        self._coverage_failures: list[str] = []
        self._steps = 0
        self._active = False
        self._entered = False
        self._finalized = False
        self._aborted = False
        self._cap_exceeded = False
        self._nonfinite_observations = 0
        self._last_step_time: float | None = None
        self._report: dict[str, Any] | None = None

    @property
    def events(self) -> list[dict[str, Any]]:
        """Return a defensive copy of the bounded aggregate event ledger."""

        with self._lock:
            return copy.deepcopy(self._events)

    @property
    def report(self) -> dict[str, Any]:
        """Return the finalized report without exposing mutable internal state."""

        with self._lock:
            if self._report is None:
                raise HookStateError("collector has not finalized successfully")
            return copy.deepcopy(self._report)

    @property
    def handles_removed(self) -> bool:
        with self._lock:
            return (
                not self._handles
                and self._removed_handle_count == self._installed_handle_count
                and not self._cleanup_failures
            )

    def __enter__(self) -> "AggregateTrainingHookCollector":
        with self._lock:
            if self._entered or self._finalized:
                raise HookStateError("collector instances are single-use")
            self._entered = True

            modules = dict(self._model.named_modules())
            missing = [name for name in self._module_names if name not in modules]
            if missing:
                raise HookConfigurationError(
                    f"module_allowlist contains unknown exact names: {missing!r}"
                )

            if self._expected_steps is not None:
                required_events = self._expected_steps * (2 * len(self._module_names) + 1)
                if required_events > self._event_cap:
                    self._cap_exceeded = True
                    raise EventCapError(
                        "event_cap cannot hold the required bounded ledger: "
                        f"need {required_events}, cap is {self._event_cap}"
                    )

            installed: list[Any] = []
            try:
                for name in self._module_names:
                    module = modules[name]
                    installed.append(
                        module.register_forward_hook(self._forward_hook(name))
                    )
                    installed.append(
                        module.register_full_backward_hook(self._backward_hook(name))
                    )
            except Exception:
                cleanup_errors = []
                for handle in reversed(installed):
                    try:
                        handle.remove()
                    except Exception as cleanup_exc:  # pragma: no cover - framework fault.
                        cleanup_errors.append(type(cleanup_exc).__name__)
                if cleanup_errors:
                    self._cleanup_failures.extend(cleanup_errors)
                    raise HookCleanupError(
                        "hook installation failed and rollback was incomplete"
                    )
                raise

            self._handles = installed
            self._installed_handle_count = len(installed)
            self._active = True
            self._last_step_time = float(self._clock())
            if not math.isfinite(self._last_step_time):
                self.close()
                raise HookConfigurationError("clock returned a non-finite value")
            return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, traceback: Any) -> bool:
        cleanup_error: HookCleanupError | None = None
        try:
            self.close()
        except HookCleanupError as caught:
            cleanup_error = caught

        if exc is not None:
            self._aborted = True
            if cleanup_error is not None and hasattr(exc, "add_note"):
                exc.add_note(str(cleanup_error))
            return False
        if cleanup_error is not None:
            raise cleanup_error
        return False

    def _forward_hook(self, module_name: str) -> Callable[..., None]:
        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            self._record_hook_event("forward", module_name, output)

        return hook

    def _backward_hook(self, module_name: str) -> Callable[..., None]:
        def hook(_module: Any, _grad_input: Any, grad_output: Any) -> None:
            self._record_hook_event("backward", module_name, grad_output)

        return hook

    def _record_hook_event(self, phase: str, module_name: str, value: Any) -> None:
        with self._lock:
            if not self._active:
                raise HookStateError("a hook fired while the collector was inactive")
            if self._expected_steps is not None and self._steps >= self._expected_steps:
                message = "hook activity exceeded expected_steps"
                self._coverage_failures.append(message)
                raise HookCoverageError(message)

            stats = aggregate_tensor_tree(value)
            key = (self._steps, phase, module_name)
            self._phase_counts[key] = self._phase_counts.get(key, 0) + 1
            self._append_event(
                {
                    "event_type": phase,
                    "step": self._steps,
                    "module": module_name,
                    "tensor_role": "module_output" if phase == "forward" else "module_output_gradient",
                    "stats": stats,
                }
            )

            if stats["elements"] == 0:
                message = (
                    f"{phase} hook for {module_name!r} observed no tensor elements "
                    f"at step {self._steps}"
                )
                self._coverage_failures.append(message)
                raise HookCoverageError(message)
            if stats["nonfinite"]:
                self._nonfinite_observations += int(stats["nonfinite"])
                raise NonFiniteTelemetryError(
                    f"{phase} hook for {module_name!r} observed "
                    f"{stats['nonfinite']} non-finite elements at step {self._steps}"
                )

    def _append_event(self, payload: dict[str, Any]) -> None:
        if len(self._events) >= self._event_cap:
            self._cap_exceeded = True
            raise EventCapError(
                f"event cap of {self._event_cap} would be exceeded"
            )
        event = {
            "sequence": len(self._events),
            "previous_sha256": self._event_chain_head,
            **payload,
        }
        event["event_sha256"] = _event_digest(event)
        self._events.append(event)
        self._event_chain_head = event["event_sha256"]

    def _validate_current_step_coverage(self) -> None:
        problems = []
        for name in self._module_names:
            for phase in ("forward", "backward"):
                observed = self._phase_counts.get((self._steps, phase, name), 0)
                if observed != 1:
                    problems.append(
                        f"step {self._steps} module {name!r} {phase} count "
                        f"was {observed}, expected 1"
                    )
        if problems:
            self._coverage_failures.extend(problems)
            raise HookCoverageError("; ".join(problems))

    def _parameter_gradient_stats(self) -> tuple[dict[str, int | float | None], dict[str, int | bool]]:
        aggregate = _Aggregate()
        expected_tensors = 0
        expected_elements = 0
        observed_tensors = 0
        observed_elements = 0
        for parameter in self._model.parameters():
            if not parameter.requires_grad:
                continue
            expected_tensors += 1
            expected_elements += int(parameter.numel())
            if parameter.grad is None:
                continue
            observed_tensors += 1
            observed_elements += int(parameter.grad.numel())
            aggregate.add_tensor(parameter.grad)
        coverage = {
            "expected_trainable_parameter_tensors": expected_tensors,
            "observed_trainable_parameter_gradient_tensors": observed_tensors,
            "missing_trainable_parameter_gradient_tensors": expected_tensors - observed_tensors,
            "expected_trainable_parameter_elements": expected_elements,
            "observed_trainable_parameter_gradient_elements": observed_elements,
            "missing_trainable_parameter_gradient_elements": expected_elements - observed_elements,
            "complete": expected_tensors == observed_tensors and expected_elements == observed_elements,
        }
        return aggregate.as_dict(), coverage

    def _gpu_memory_stats(
        self, supplied: Mapping[str, Any] | None = None
    ) -> dict[str, bool | int]:
        runtime = _require_torch()
        if supplied is not None:
            allowed = {
                "allocated_bytes",
                "reserved_bytes",
                "peak_allocated_bytes",
                "peak_reserved_bytes",
                "max_allocated_bytes",
                "max_reserved_bytes",
                "device_count",
                "cuda_available",
            }
            unknown = set(supplied) - allowed
            if unknown:
                raise HookConfigurationError(
                    f"gpu_memory contains unsupported fields: {sorted(unknown)!r}"
                )
            result: dict[str, bool | int] = {}
            for key, value in supplied.items():
                if key == "cuda_available":
                    if not isinstance(value, bool):
                        raise HookConfigurationError(
                            "gpu_memory.cuda_available must be a boolean"
                        )
                    result[key] = value
                else:
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise HookConfigurationError(
                            f"gpu_memory.{key} must be an integer >= 0"
                        )
                    result[key] = value
            cuda_available = bool(runtime.cuda.is_available())
            model_cuda_devices = {
                int(parameter.device.index)
                if parameter.device.index is not None
                else int(runtime.cuda.current_device())
                for parameter in self._model.parameters()
                if parameter.device.type == "cuda"
            }
            result.setdefault("cuda_available", cuda_available)
            result.setdefault("device_count", len(model_cuda_devices))
            result.setdefault("allocated_bytes", 0)
            result.setdefault("reserved_bytes", 0)
            if "peak_allocated_bytes" not in result:
                result["peak_allocated_bytes"] = int(
                    result.pop("max_allocated_bytes", 0)
                )
            else:
                result.pop("max_allocated_bytes", None)
            if "peak_reserved_bytes" not in result:
                result["peak_reserved_bytes"] = int(
                    result.pop("max_reserved_bytes", 0)
                )
            else:
                result.pop("max_reserved_bytes", None)
            return result

        cuda_available = bool(runtime.cuda.is_available())
        device_indices: set[int] = set()
        if cuda_available:
            for parameter in self._model.parameters():
                if parameter.device.type == "cuda":
                    index = parameter.device.index
                    if index is None:
                        index = int(runtime.cuda.current_device())
                    device_indices.add(int(index))

        allocated = 0
        reserved = 0
        max_allocated = 0
        max_reserved = 0
        for index in sorted(device_indices):
            allocated += int(runtime.cuda.memory_allocated(index))
            reserved += int(runtime.cuda.memory_reserved(index))
            max_allocated += int(runtime.cuda.max_memory_allocated(index))
            max_reserved += int(runtime.cuda.max_memory_reserved(index))
        return {
            "cuda_available": cuda_available,
            "device_count": len(device_indices),
            "allocated_bytes": allocated,
            "reserved_bytes": reserved,
            "peak_allocated_bytes": max_allocated,
            "peak_reserved_bytes": max_reserved,
        }

    def _loss_scalar(self, loss: Any) -> tuple[float | None, bool]:
        runtime = _require_torch()
        if runtime.is_tensor(loss):
            if int(loss.numel()) != 1:
                raise HookConfigurationError("loss tensor must contain exactly one element")
            value = float(loss.detach().item())
        elif isinstance(loss, (int, float)) and not isinstance(loss, bool):
            value = float(loss)
        else:
            raise HookConfigurationError("loss must be a scalar number or one-element tensor")
        if not math.isfinite(value):
            return None, True
        return value, False

    def step(
        self,
        loss: Any,
        tokens: int | None = None,
        *,
        step: int | None = None,
        epoch: int | None = None,
        batch_index: int | None = None,
        model: Any | None = None,
        learning_rate: float | None = None,
        input_tokens: int | None = None,
        target_tokens: int | None = None,
        truncated_records: int | None = None,
        batch_manifest_sha256: str | None = None,
        duration_seconds: float | None = None,
        gpu_memory: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Seal one training step after backward and before the optimizer update."""

        with self._lock:
            if not self._active:
                raise HookStateError("step requires an active collector context")
            if model is not None and model is not self._model:
                raise HookConfigurationError("step model must be the collector model")
            if step is not None:
                if isinstance(step, bool) or not isinstance(step, int) or step < 0:
                    raise HookConfigurationError("step must be an integer >= 0")
                if step != self._steps:
                    raise HookCoverageError(
                        f"step index was {step}, expected {self._steps}"
                    )
            for name, value in (("epoch", epoch), ("batch_index", batch_index)):
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    raise HookConfigurationError(f"{name} must be an integer >= 0")
            if tokens is not None and input_tokens is not None and tokens != input_tokens:
                raise HookConfigurationError("tokens and input_tokens disagree")
            if tokens is None:
                tokens = input_tokens
            if tokens is None:
                raise HookConfigurationError("tokens or input_tokens is required")
            if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 1:
                raise HookConfigurationError("tokens must be an integer >= 1")
            if target_tokens is not None and (
                isinstance(target_tokens, bool)
                or not isinstance(target_tokens, int)
                or target_tokens < 0
            ):
                raise HookConfigurationError("target_tokens must be an integer >= 0")
            if truncated_records is not None and (
                isinstance(truncated_records, bool)
                or not isinstance(truncated_records, int)
                or truncated_records < 0
            ):
                raise HookConfigurationError(
                    "truncated_records must be an integer >= 0"
                )
            if batch_manifest_sha256 is not None and (
                not isinstance(batch_manifest_sha256, str)
                or SHA256_PATTERN.fullmatch(batch_manifest_sha256) is None
            ):
                raise HookConfigurationError(
                    "batch_manifest_sha256 must be a lowercase SHA-256 digest"
                )
            if learning_rate is not None:
                learning_rate = _finite_number(
                    learning_rate, "learning_rate", minimum=0.0
                )
            if self._expected_steps is not None and self._steps >= self._expected_steps:
                message = "step count would exceed expected_steps"
                self._coverage_failures.append(message)
                raise HookCoverageError(message)

            self._validate_current_step_coverage()
            loss_value, loss_nonfinite = self._loss_scalar(loss)
            gradient_stats, gradient_coverage = self._parameter_gradient_stats()

            now = float(self._clock())
            if not math.isfinite(now):
                raise HookConfigurationError("clock returned a non-finite value")
            if duration_seconds is None:
                if self._last_step_time is None:  # Defensive; active implies initialized.
                    raise HookStateError("step timer was not initialized")
                duration = now - self._last_step_time
                if not math.isfinite(duration) or duration < 0:
                    raise HookConfigurationError("clock must be finite and monotonic")
            else:
                duration = _finite_number(
                    duration_seconds, "duration_seconds", minimum=0.0
                )

            event_payload = {
                "event_type": "step",
                "step": self._steps,
                "loss": loss_value,
                "loss_nonfinite": loss_nonfinite,
                "parameter_gradients": gradient_stats,
                "parameter_gradient_role": "all_model_parameter_gradients_before_optimizer_step",
                "parameter_gradient_coverage": gradient_coverage,
                "tokens": tokens,
                "duration_seconds": duration,
                "gpu_memory": self._gpu_memory_stats(gpu_memory),
            }
            if target_tokens is not None:
                event_payload["target_tokens"] = target_tokens
            if epoch is not None:
                event_payload["epoch"] = epoch
            if batch_index is not None:
                event_payload["batch_index"] = batch_index
            if learning_rate is not None:
                event_payload["learning_rate"] = learning_rate
            if truncated_records is not None:
                event_payload["truncated_records"] = truncated_records
            if batch_manifest_sha256 is not None:
                event_payload["batch_manifest_sha256"] = batch_manifest_sha256
            self._append_event(event_payload)
            self._last_step_time = now
            self._steps += 1

            if loss_nonfinite:
                self._nonfinite_observations += 1
                raise NonFiniteTelemetryError(
                    f"loss was non-finite at step {self._steps - 1}"
                )
            if gradient_stats["elements"] == 0:
                message = f"no parameter gradients were observed at step {self._steps - 1}"
                self._coverage_failures.append(message)
                raise HookCoverageError(message)
            if not gradient_coverage["complete"]:
                message = (
                    "not every trainable parameter had a gradient at step "
                    f"{self._steps - 1}: missing "
                    f"{gradient_coverage['missing_trainable_parameter_gradient_tensors']} tensors / "
                    f"{gradient_coverage['missing_trainable_parameter_gradient_elements']} elements"
                )
                self._coverage_failures.append(message)
                raise HookCoverageError(message)
            if gradient_stats["nonfinite"]:
                self._nonfinite_observations += int(gradient_stats["nonfinite"])
                raise NonFiniteTelemetryError(
                    f"parameter gradients contained {gradient_stats['nonfinite']} "
                    f"non-finite elements at step {self._steps - 1}"
                )
            return copy.deepcopy(self._events[-1])

    def close(self) -> None:
        """Remove every installed hook handle; safe to call more than once."""

        with self._lock:
            if not self._handles:
                self._active = False
                if self._cleanup_failures:
                    raise HookCleanupError("one or more hook handles were not removed")
                return

            failures = []
            failed_handles = []
            handles = self._handles
            self._handles = []
            for handle in reversed(handles):
                try:
                    handle.remove()
                    self._removed_handle_count += 1
                except Exception as exc:  # pragma: no cover - framework fault.
                    failures.append(type(exc).__name__)
                    failed_handles.append(handle)
            # Preserve handles whose removal failed for retry/inspection and
            # ensure this collector can never finalize as a successful run.
            self._handles = list(reversed(failed_handles))
            self._active = False
            if failures:
                self._cleanup_failures.extend(failures)
                raise HookCleanupError(
                    f"failed to remove {len(failures)} hook handle(s)"
                )

    def remove(self) -> None:
        """Compatibility alias for :meth:`close`."""

        self.close()

    def _verify_event_chain(self) -> None:
        previous = self._event_chain_genesis
        for sequence, stored in enumerate(self._events):
            if stored.get("sequence") != sequence:
                raise EventIntegrityError(
                    f"event sequence mismatch at position {sequence}"
                )
            if stored.get("previous_sha256") != previous:
                raise EventIntegrityError(
                    f"event predecessor mismatch at position {sequence}"
                )
            candidate = dict(stored)
            claimed = candidate.pop("event_sha256", None)
            replayed = _event_digest(candidate)
            if claimed != replayed:
                raise EventIntegrityError(
                    f"event digest mismatch at position {sequence}"
                )
            previous = replayed
        if previous != self._event_chain_head:
            raise EventIntegrityError("event chain head does not match the ledger")

    def _verify_final_coverage(self, expected_steps: int) -> dict[str, Any]:
        per_module: dict[str, dict[str, int]] = {}
        failures = list(self._coverage_failures)
        for name in self._module_names:
            forward_count = sum(
                self._phase_counts.get((step, "forward", name), 0)
                for step in range(expected_steps)
            )
            backward_count = sum(
                self._phase_counts.get((step, "backward", name), 0)
                for step in range(expected_steps)
            )
            per_module[name] = {
                "forward": forward_count,
                "backward": backward_count,
            }
            if forward_count != expected_steps:
                failures.append(
                    f"module {name!r} forward total was {forward_count}, "
                    f"expected {expected_steps}"
                )
            if backward_count != expected_steps:
                failures.append(
                    f"module {name!r} backward total was {backward_count}, "
                    f"expected {expected_steps}"
                )

        required_hook_events = expected_steps * len(self._module_names)
        observed_forward = sum(item["forward"] for item in per_module.values())
        observed_backward = sum(item["backward"] for item in per_module.values())
        expected_event_count = expected_steps * (2 * len(self._module_names) + 1)
        if len(self._events) != expected_event_count:
            failures.append(
                f"event count was {len(self._events)}, expected {expected_event_count}"
            )
        if failures:
            raise HookCoverageError("; ".join(failures))

        return {
            "required_forward_events": required_hook_events,
            "observed_forward_events": observed_forward,
            "required_backward_events": required_hook_events,
            "observed_backward_events": observed_backward,
            "per_module": per_module,
            "handles_removed": self.handles_removed,
        }

    def finalize(self, expected_steps: int | None = None) -> dict[str, Any]:
        """Remove hooks, replay integrity, and return a fail-closed report."""

        with self._lock:
            if expected_steps is not None:
                expected_steps = _strict_positive_integer(
                    expected_steps, "expected_steps"
                )
            if self._report is not None:
                if (
                    expected_steps is not None
                    and expected_steps != self._report["expected_steps"]
                ):
                    raise HookConfigurationError(
                        "expected_steps disagrees with the finalized report"
                    )
                return copy.deepcopy(self._report)
            if not self._entered:
                raise HookStateError("collector was never entered")

            if expected_steps is not None:
                if (
                    self._expected_steps is not None
                    and expected_steps != self._expected_steps
                ):
                    raise HookConfigurationError(
                        "finalize expected_steps disagrees with constructor"
                    )
            elif self._expected_steps is not None:
                expected_steps = self._expected_steps
            else:
                expected_steps = self._steps

            self.close()
            if not self.handles_removed:
                raise HookCleanupError("not all installed hook handles were removed")
            required_event_capacity = expected_steps * (
                2 * len(self._module_names) + 1
            )
            if required_event_capacity > self._event_cap:
                raise EventCapError(
                    "event_cap cannot hold the required bounded ledger: "
                    f"need {required_event_capacity}, cap is {self._event_cap}"
                )
            if self._cap_exceeded or len(self._events) > self._event_cap:
                raise EventCapError("event cap was exceeded or could not cover the run")
            if self._nonfinite_observations:
                raise NonFiniteTelemetryError(
                    f"run observed {self._nonfinite_observations} non-finite values"
                )
            if self._aborted:
                raise HookCoverageError(
                    "collector context exited with an exception; the run is incomplete"
                )
            self._verify_event_chain()

            if expected_steps < 1:
                raise HookCoverageError("at least one successful training step is required")
            if self._steps != expected_steps:
                raise HookCoverageError(
                    f"successful step count was {self._steps}, expected {expected_steps}"
                )
            coverage = self._verify_final_coverage(expected_steps)
            observed_forward = coverage["observed_forward_events"]
            observed_backward = coverage["observed_backward_events"]

            parameter_tensors = 0
            parameter_elements = 0
            trainable_parameter_tensors = 0
            trainable_parameter_elements = 0
            for parameter in self._model.parameters():
                parameter_tensors += 1
                parameter_elements += int(parameter.numel())
                if parameter.requires_grad:
                    trainable_parameter_tensors += 1
                    trainable_parameter_elements += int(parameter.numel())

            report = {
                "schema_version": SCHEMA_VERSION,
                "collector": "aggregate_training_hooks",
                "status": "pass",
                "aggregate_only": True,
                "raw_tensors_retained": False,
                "raw_text_retained": False,
                "raw_token_arrays_retained": False,
                "allowlisted_modules": list(self._module_names),
                "expected_steps": expected_steps,
                "observed_steps": self._steps,
                "coverage_status": "complete",
                "observed_forward_events": observed_forward,
                "observed_backward_events": observed_backward,
                "nonfinite_elements": 0,
                "handles_removed": True,
                "model_parameters": {
                    "count": parameter_tensors,
                    "elements": parameter_elements,
                    "trainable_count": trainable_parameter_tensors,
                    "trainable_elements": trainable_parameter_elements,
                },
                "coverage": coverage,
                "event_cap": self._event_cap,
                "max_events": self._event_cap,
                "event_count": len(self._events),
                "event_chain_genesis_sha256": self._event_chain_genesis,
                "context_bound": self._event_chain_genesis != GENESIS_SHA256,
                "event_chain_head_sha256": self._event_chain_head,
                "events": copy.deepcopy(self._events),
            }
            _canonical_bytes(report)
            self._report = report
            self._finalized = True
            return copy.deepcopy(report)


# Concise aliases for callers that do not need the longer assurance-oriented name.
TrainingHookCollector = AggregateTrainingHookCollector
LLMTrainingHookCollector = AggregateTrainingHookCollector


__all__ = [
    "AggregateTrainingHookCollector",
    "EventCapError",
    "EventIntegrityError",
    "HookCleanupError",
    "HookConfigurationError",
    "HookCoverageError",
    "HookStateError",
    "LLMTrainingHookCollector",
    "NonFiniteTelemetryError",
    "STAT_KEYS",
    "TorchUnavailableError",
    "TrainingHookCollector",
    "TrainingHookError",
    "aggregate_tensor_tree",
]
