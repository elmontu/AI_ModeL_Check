from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from model_release_assurance.experimental_finite_wrapper import (
    ClosedHiddenRecordCategoricalWrapper,
    ClosedWrapperQueryError,
    FORBIDDEN_RECIPIENT_FIELDS,
    WrapperConformanceError,
    validate_closed_hidden_record_wrapper,
    validate_wrapper_interface_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "reproduction" / "model-backed-finite-channel" / "config.json"


def wrapper_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["finite_wrapper"]


def aggregate_population(wrapper: dict) -> dict[str, tuple[int, ...]]:
    width = len(wrapper["observation_ids"])
    return {
        "out": tuple(index + 1 for index in range(width)),
        "in": tuple(width - index for index in range(width)),
    }


class ClosedHiddenRecordWrapperConformanceTests(unittest.TestCase):
    def test_valid_wrapper_emits_only_one_registered_string(self) -> None:
        config = wrapper_config()
        wrapper = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=config,
            aggregate_population=aggregate_population(config),
            sealed_state="out",
            issuer_seed=7,
        )

        transcript = wrapper.query()

        self.assertIs(type(transcript), str)
        self.assertIn(transcript, config["observation_ids"])
        self.assertEqual(
            {name for name in dir(wrapper) if not name.startswith("_")},
            {"query"},
        )
        self.assertEqual(repr(wrapper), "<ClosedHiddenRecordCategoricalWrapper sealed>")

    def test_all_caller_fields_and_positional_values_are_refused_constantly(self) -> None:
        config = wrapper_config()
        population = aggregate_population(config)
        messages = set()
        for index, field in enumerate(FORBIDDEN_RECIPIENT_FIELDS):
            with self.subTest(field=field):
                wrapper = ClosedHiddenRecordCategoricalWrapper(
                    wrapper_config=config,
                    aggregate_population=population,
                    sealed_state="in",
                    issuer_seed=100 + index,
                )
                with self.assertRaises(ClosedWrapperQueryError) as caught:
                    wrapper.query(**{field: object()})
                messages.add(str(caught.exception))

        wrapper = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=config,
            aggregate_population=population,
            sealed_state="in",
            issuer_seed=200,
        )
        with self.assertRaises(ClosedWrapperQueryError) as caught:
            wrapper.query(object())
        messages.add(str(caught.exception))
        self.assertEqual(
            messages,
            {"closed wrapper query accepts no caller-supplied inputs"},
        )

    def test_query_budget_is_enforced_by_the_executable_wrapper(self) -> None:
        config = wrapper_config()
        wrapper = ClosedHiddenRecordCategoricalWrapper(
            wrapper_config=config,
            aggregate_population=aggregate_population(config),
            sealed_state="out",
            issuer_seed=3,
        )
        wrapper.query()
        with self.assertRaisesRegex(
            ClosedWrapperQueryError,
            "^closed wrapper query budget exhausted$",
        ):
            wrapper.query()

    def test_unknown_states_and_population_outputs_fail_closed(self) -> None:
        config = wrapper_config()
        population = aggregate_population(config)
        with self.assertRaisesRegex(WrapperConformanceError, "sealed state is not registered"):
            ClosedHiddenRecordCategoricalWrapper(
                wrapper_config=config,
                aggregate_population=population,
                sealed_state="unknown",
                issuer_seed=1,
            )

        invalid_populations = []
        extra_state = dict(population)
        extra_state["unknown"] = extra_state["out"]
        invalid_populations.append(extra_state)
        missing_state = {"out": population["out"]}
        invalid_populations.append(missing_state)
        wrong_width = {"out": population["out"][:-1], "in": population["in"]}
        invalid_populations.append(wrong_width)
        unknown_output = {
            "out": {
                **dict(zip(config["observation_ids"], population["out"], strict=True)),
                "unknown_output": 1,
            },
            "in": dict(zip(config["observation_ids"], population["in"], strict=True)),
        }
        invalid_populations.append(unknown_output)
        negative = {"out": (-1,) + population["out"][1:], "in": population["in"]}
        invalid_populations.append(negative)
        boolean = {"out": (True,) + population["out"][1:], "in": population["in"]}
        invalid_populations.append(boolean)
        empty = {
            "out": tuple(0 for _ in population["out"]),
            "in": population["in"],
        }
        invalid_populations.append(empty)

        for index, candidate in enumerate(invalid_populations):
            with self.subTest(index=index), self.assertRaises(WrapperConformanceError):
                ClosedHiddenRecordCategoricalWrapper(
                    wrapper_config=config,
                    aggregate_population=candidate,
                    sealed_state="out",
                    issuer_seed=1,
                )

    def test_error_timeout_and_every_category_have_no_metadata_shape(self) -> None:
        config = wrapper_config()
        alphabet = config["observation_ids"]
        observed = []
        for index, expected in enumerate(alphabet):
            counts = tuple(1 if position == index else 0 for position in range(len(alphabet)))
            wrapper = ClosedHiddenRecordCategoricalWrapper(
                wrapper_config=config,
                aggregate_population={"out": counts, "in": counts},
                sealed_state="out",
                issuer_seed=index,
            )
            transcript = wrapper.query()
            self.assertIs(type(transcript), str)
            self.assertEqual(transcript, expected)
            observed.append(transcript)

        self.assertEqual(observed, alphabet)
        self.assertIn(config["error_observation_id"], observed)
        self.assertIn(config["timeout_observation_id"], observed)
        self.assertFalse(any(
            token in transcript.lower()
            for transcript in observed
            for token in ("duration", "latency", "timestamp", "exception", "traceback")
        ))

    def test_interface_config_mismatches_fail_closed(self) -> None:
        original = wrapper_config()
        mutations: list[dict] = []

        for field in (
            "candidate_record_visible",
            "model_or_weights_visible",
            "raw_loss_visible",
            "timing_visible",
            "identifiers_or_metadata_visible",
            "arbitrary_query_path",
        ):
            candidate = copy.deepcopy(original)
            candidate[field] = True
            mutations.append(candidate)

        candidate = copy.deepcopy(original)
        candidate["mechanism"] = "ordinary_prediction_api"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["query_budget"] = 2
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["query_budget"] = True
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["recipient_input_fields"] = ["record"]
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["recipient_observes_only"] = "symbol and timing"
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["observation_ids"].append(candidate["observation_ids"][0])
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["observation_ids"].remove(candidate["timeout_observation_id"])
        mutations.append(candidate)
        candidate = copy.deepcopy(original)
        candidate["observation_ids"].remove("state_independent_erasure")
        mutations.append(candidate)

        for index, candidate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(WrapperConformanceError):
                validate_wrapper_interface_config(candidate)

    def test_bounded_harness_reports_checks_and_explicit_scope_limits(self) -> None:
        config = wrapper_config()
        report = validate_closed_hidden_record_wrapper(
            config,
            aggregate_population=aggregate_population(config),
        )

        self.assertTrue(report["conformant"])
        self.assertEqual(report["interface"]["recipient_input_fields"], [])
        self.assertEqual(report["interface"]["transcript_metadata_fields"], [])
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        serialized = json.dumps(report).lower()
        self.assertIn("operating-system side channels are not tested", serialized)
        self.assertIn("real serving-endpoint enforcement are not proven", serialized)
        self.assertNotIn("issuer_seed", serialized)
        self.assertNotIn("sealed_state", serialized)


if __name__ == "__main__":
    unittest.main()
