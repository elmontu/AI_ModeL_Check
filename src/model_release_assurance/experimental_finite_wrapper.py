"""Executable conformance harness for the experimental finite-channel wrapper.

This module deliberately implements a very small *recipient-visible* surface:
``query() -> str``.  An experiment issuer seals a hidden state and an aggregate
categorical population before handing the wrapper to a recipient.  The
recipient cannot supply a record, model, loss, identifier, or query path.

This is executable evidence about the Python wrapper and its returned value. It
is not a process-isolation, operating-system side-channel, authentication, or
production-endpoint proof.  In particular, Python reflection is not a security
boundary; a real service must enforce the same interface outside the
recipient's process before this abstraction can describe that service.
"""

from __future__ import annotations

import bisect
import random
from collections.abc import Mapping, Sequence
from typing import Any, Final


class WrapperConformanceError(ValueError):
    """The wrapper configuration or sealed aggregate population is invalid."""


class ClosedWrapperQueryError(RuntimeError):
    """A caller tried to exceed the closed wrapper's visible interface."""


_CLOSED_INPUT_MESSAGE: Final = "closed wrapper query accepts no caller-supplied inputs"
_BUDGET_MESSAGE: Final = "closed wrapper query budget exhausted"
_EXPECTED_STATES: Final = ("out", "in")
_REQUIRED_FALSE_FIELDS: Final = (
    "candidate_record_visible",
    "model_or_weights_visible",
    "raw_loss_visible",
    "timing_visible",
    "identifiers_or_metadata_visible",
    "arbitrary_query_path",
)

# These probes cover both direct candidate material and common aliases.  The
# implementation rejects every positional argument and keyword, not only this
# audit roster.
FORBIDDEN_RECIPIENT_FIELDS: Final = (
    "candidate_record",
    "record",
    "features",
    "prompt",
    "model",
    "weights",
    "raw_loss",
    "timing",
    "identifier",
    "metadata",
    "query_path",
)


def _fail(message: str) -> None:
    raise WrapperConformanceError(message)


def validate_wrapper_interface_config(wrapper_config: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate the closed, one-query interface and return its alphabet.

    The check is intentionally stricter than ordinary duck typing.  Every
    visibility flag must be the literal boolean ``False`` and the caller field
    list must be exactly empty.  This prevents truthy/falsy substitutes from
    silently weakening a preregistered interface.
    """

    if not isinstance(wrapper_config, Mapping):
        _fail("wrapper configuration must be an object")
    if wrapper_config.get("mechanism") != "one_query_closed_hidden_record_sampler":
        _fail("wrapper mechanism does not identify the registered closed sampler")
    if type(wrapper_config.get("query_budget")) is not int or wrapper_config["query_budget"] != 1:
        _fail("closed wrapper query budget must be the integer one")
    if wrapper_config.get("recipient_input_fields") != []:
        _fail("closed wrapper recipient input field list must be exactly empty")
    if wrapper_config.get("recipient_observes_only") != (
        "one categorical symbol from the complete observation_ids list"
    ):
        _fail("recipient-visible output description does not match the closed wrapper")
    for field in _REQUIRED_FALSE_FIELDS:
        if wrapper_config.get(field) is not False:
            _fail("a recipient-visible channel is enabled or unspecified")

    observation_ids = wrapper_config.get("observation_ids")
    if not isinstance(observation_ids, list) or not observation_ids:
        _fail("observation_ids must be a non-empty list")
    if any(not isinstance(value, str) or not value for value in observation_ids):
        _fail("every observation identifier must be a non-empty string")
    if len(observation_ids) != len(set(observation_ids)):
        _fail("observation identifiers must be unique")
    alphabet = tuple(observation_ids)

    special_fields = (
        "nonfinite_observation_id",
        "error_observation_id",
        "timeout_observation_id",
    )
    for field in special_fields:
        value = wrapper_config.get(field)
        if not isinstance(value, str) or value not in alphabet:
            _fail("a totalized failure observation is absent from the alphabet")
    if "state_independent_erasure" not in alphabet:
        _fail("the registered state-independent erasure symbol is absent")
    return alphabet


def _validate_aggregate_population(
    aggregate_population: Mapping[str, Sequence[int] | Mapping[str, int]],
    alphabet: Sequence[str],
) -> dict[str, tuple[int, ...]]:
    if not isinstance(aggregate_population, Mapping):
        _fail("aggregate population must be an object")
    if tuple(aggregate_population) != _EXPECTED_STATES:
        _fail("aggregate population must contain the registered states in order")

    validated: dict[str, tuple[int, ...]] = {}
    for state in _EXPECTED_STATES:
        row = aggregate_population[state]
        if isinstance(row, Mapping):
            if tuple(row) != tuple(alphabet):
                _fail("aggregate output identifiers do not match the registered alphabet")
            counts = tuple(row[observation_id] for observation_id in alphabet)
        elif not isinstance(row, (str, bytes)) and isinstance(row, Sequence):
            counts = tuple(row)
            if len(counts) != len(alphabet):
                _fail("aggregate count width does not match the registered alphabet")
        else:
            _fail("each sealed state population must be a count sequence or observation map")
        if any(type(value) is not int or value < 0 for value in counts):
            _fail("aggregate counts must be non-negative integers")
        if sum(counts) <= 0:
            _fail("each sealed state population must be non-empty")
        validated[state] = tuple(counts)
    return validated


def _validate_erasure_probability(
    value: Mapping[str, Any] | None,
) -> tuple[int, int]:
    if value is None:
        return 0, 1
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        _fail("state-independent erasure must be an exact rational object")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
        or numerator < 0
        or numerator >= denominator
    ):
        _fail("state-independent erasure must lie in [0, 1)")
    return numerator, denominator


class ClosedHiddenRecordCategoricalWrapper:
    """A single-use capability returning one categorical observation only.

    Construction is the issuer/auditor boundary.  ``query`` is the entire
    intended recipient boundary.  Private slots reduce accidental disclosure
    in logs and ``repr`` but, as documented above, do not make Python process
    introspection a security boundary.
    """

    __slots__ = (
        "__alphabet",
        "__cumulative_counts",
        "__erasure_denominator",
        "__erasure_index",
        "__erasure_numerator",
        "__population_size",
        "__rng",
        "__used",
    )

    def __init__(
        self,
        *,
        wrapper_config: Mapping[str, Any],
        aggregate_population: Mapping[
            str,
            Sequence[int] | Mapping[str, int],
        ],
        sealed_state: str,
        issuer_seed: int,
        state_independent_erasure: Mapping[str, Any] | None = None,
    ) -> None:
        alphabet = validate_wrapper_interface_config(wrapper_config)
        population = _validate_aggregate_population(aggregate_population, alphabet)
        erasure_numerator, erasure_denominator = _validate_erasure_probability(
            state_independent_erasure
        )
        if sealed_state not in _EXPECTED_STATES:
            _fail("sealed state is not registered")
        if type(issuer_seed) is not int:
            _fail("issuer seed must be an integer")

        running = 0
        cumulative_counts: list[int] = []
        for count in population[sealed_state]:
            running += count
            cumulative_counts.append(running)
        self.__alphabet = alphabet
        self.__cumulative_counts = tuple(cumulative_counts)
        self.__erasure_numerator = erasure_numerator
        self.__erasure_denominator = erasure_denominator
        self.__erasure_index = alphabet.index("state_independent_erasure")
        self.__population_size = running
        self.__rng = random.Random(issuer_seed)
        self.__used = False

    def __repr__(self) -> str:
        return "<ClosedHiddenRecordCategoricalWrapper sealed>"

    def query(self, *caller_args: Any, **caller_fields: Any) -> str:
        """Return one registered symbol, accepting no recipient-supplied input."""

        if caller_args or caller_fields:
            raise ClosedWrapperQueryError(_CLOSED_INPUT_MESSAGE)
        if self.__used:
            raise ClosedWrapperQueryError(_BUDGET_MESSAGE)
        # Consume the capability before drawing so even an unexpected internal
        # exception cannot accidentally leave a second-query path open.
        self.__used = True
        draw = self.__rng.randrange(self.__population_size)
        index = bisect.bisect_right(self.__cumulative_counts, draw)
        if (
            self.__erasure_numerator
            and self.__rng.randrange(self.__erasure_denominator)
            < self.__erasure_numerator
        ):
            index = self.__erasure_index
        return self.__alphabet[index]


def validate_closed_hidden_record_wrapper(
    wrapper_config: Mapping[str, Any],
    *,
    aggregate_population: Mapping[
        str,
        Sequence[int] | Mapping[str, int],
    ] | None = None,
    state_independent_erasure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute bounded conformance probes and return an aggregate-only result.

    The optional population exists so the registered experiment can replay the
    harness against its own aggregate finite population.  It contains counts,
    never caller records, models, losses, timing, or identifiers.  The report
    intentionally retains no sampled transcript value.
    """

    alphabet = validate_wrapper_interface_config(wrapper_config)
    if aggregate_population is None:
        # Every output is reachable in the probe population.  Tests below also
        # force each category separately, including error and timeout symbols.
        aggregate_population = {
            "out": tuple(1 for _ in alphabet),
            "in": tuple(1 for _ in alphabet),
        }
    population = _validate_aggregate_population(aggregate_population, alphabet)
    erasure_numerator, erasure_denominator = _validate_erasure_probability(
        state_independent_erasure
    )
    erasure = {
        "numerator": erasure_numerator,
        "denominator": erasure_denominator,
    }
    checks: list[dict[str, Any]] = []

    def record(check_id: str, passed: bool) -> None:
        checks.append({"check_id": check_id, "passed": passed})

    # One ordinary query: the returned Python value itself is the transcript.
    ordinary = ClosedHiddenRecordCategoricalWrapper(
        wrapper_config=wrapper_config,
        aggregate_population=population,
        sealed_state="out",
        issuer_seed=1101,
        state_independent_erasure=erasure,
    )
    output = ordinary.query()
    record("exactly_one_categorical_symbol", type(output) is str and output in alphabet)
    record("no_transcript_timing_or_metadata", type(output) is str)
    try:
        ordinary.query()
    except ClosedWrapperQueryError as exc:
        record("second_query_refused", str(exc) == _BUDGET_MESSAGE)
    else:
        record("second_query_refused", False)

    caller_fields_refused = True
    refusal_messages: set[str] = set()
    for offset, field in enumerate(FORBIDDEN_RECIPIENT_FIELDS):
        probe = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=wrapper_config,
            aggregate_population=population,
            sealed_state="in",
            issuer_seed=1200 + offset,
            state_independent_erasure=erasure,
        )
        try:
            probe.query(**{field: "opaque-caller-value"})
        except ClosedWrapperQueryError as exc:
            refusal_messages.add(str(exc))
        else:
            caller_fields_refused = False
    positional = ClosedHiddenRecordCategoricalWrapper(
        wrapper_config=wrapper_config,
        aggregate_population=population,
        sealed_state="in",
        issuer_seed=1301,
        state_independent_erasure=erasure,
    )
    try:
        positional.query("opaque-caller-value")
    except ClosedWrapperQueryError as exc:
        refusal_messages.add(str(exc))
    else:
        caller_fields_refused = False
    record(
        "all_caller_fields_refused_with_constant_error",
        caller_fields_refused and refusal_messages == {_CLOSED_INPUT_MESSAGE},
    )

    all_categories_totalized = True
    for index, expected in enumerate(alphabet):
        forced_counts = tuple(1 if position == index else 0 for position in range(len(alphabet)))
        forced_population = {"out": forced_counts, "in": forced_counts}
        probe = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=wrapper_config,
            aggregate_population=forced_population,
            sealed_state="out",
            issuer_seed=1400 + index,
        )
        all_categories_totalized = all_categories_totalized and probe.query() == expected
    record("complete_registered_alphabet_is_totalized", all_categories_totalized)

    # Compare the executable wrapper to a separately replayed deterministic
    # schedule. Only aggregate match counts are retained, never transcripts.
    non_erasure_index = next(
        index for index, value in enumerate(alphabet)
        if value != "state_independent_erasure"
    )
    forced_counts = tuple(
        1 if index == non_erasure_index else 0 for index in range(len(alphabet))
    )
    forced_population = {"out": forced_counts, "in": forced_counts}
    expected_erased = 0
    observed_erased = 0
    erasure_symbol = "state_independent_erasure"
    probe_count = 100
    for seed in range(1600, 1600 + probe_count):
        expected_rng = random.Random(seed)
        expected_rng.randrange(1)
        expected_is_erased = bool(
            erasure_numerator
            and expected_rng.randrange(erasure_denominator) < erasure_numerator
        )
        expected_erased += int(expected_is_erased)
        probe = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=wrapper_config,
            aggregate_population=forced_population,
            sealed_state="out",
            issuer_seed=seed,
            state_independent_erasure=erasure,
        )
        observed_erased += int(probe.query() == erasure_symbol)
    record(
        "exact_state_independent_erasure_schedule_replayed",
        observed_erased == expected_erased,
    )

    public_names = {
        name for name in dir(ordinary)
        if not name.startswith("_")
    }
    record("no_public_metadata_accessors", public_names == {"query"})

    passed = all(bool(value["passed"]) for value in checks)
    return {
        "schema_version": "1.0",
        "conformant": passed,
        "interface": {
            "recipient_callable": "query()",
            "return_type": "categorical_symbol_string",
            "query_budget": 1,
            "recipient_input_fields": [],
            "transcript_metadata_fields": [],
            "registered_observation_count": len(alphabet),
            "state_independent_erasure": erasure,
        },
        "erasure_probe": {
            "probe_count": probe_count,
            "expected_erasure_count": expected_erased,
            "observed_erasure_count": observed_erased,
            "transcripts_retained": False,
        },
        "checks": checks,
        "limitations": [
            "Python object reflection and memory inspection are not a security boundary.",
            "Process, scheduler, transport, network, hardware, and operating-system side channels are not tested.",
            "Authentication, rate limiting, deployment isolation, and real serving-endpoint enforcement are not proven.",
            "Conformance is conditional on the supplied aggregate finite population and registered categorical interface.",
        ],
    }
