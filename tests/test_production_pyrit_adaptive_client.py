"""No-provider transport tests for exact adaptive role budgets and requests."""
from __future__ import annotations
import copy
import json
import unittest
from unittest import mock
from model_release_assurance.production_adapters.contracts import canonical_bytes
from model_release_assurance.production_pyrit_adaptive import client as c, protocol as p

MESSAGES = [{"role": "system", "content": "Public test system."}, {"role": "user", "content": "Public test prompt."}]


def envelope(text="Public grammar response."):
    return {"model": p.MODEL_NAME, "message": {"role": "assistant", "content": text},
        "done": True, "done_reason": "stop", "eval_count": 1, "prompt_eval_count": 1}


class Response:
    def __init__(self, data, *, raw=None, content_type="application/json", status=200):
        self.raw = canonical_bytes(data) if raw is None else raw
        self.headers = {"Content-Type": content_type}
        self.status = status
        self.read_limits = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, maximum):
        self.read_limits.append(maximum)
        return self.raw[:maximum]


class Opener:
    def __init__(self):
        self.calls = []
        self.responses = []
    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        if not self.responses: raise AssertionError("An unexpected provider call was attempted")
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response


class AdaptiveClientTests(unittest.TestCase):
    def setUp(self):
        self.opener = Opener()
        patch = mock.patch.object(c, "build_opener", return_value=self.opener)
        self.start = patch.start()
        self.addCleanup(patch.stop)
        self.client = c.AdaptiveLoopbackClient()
    def bind(self):
        self.opener.responses.append(Response({"models": [{"name": p.MODEL_NAME, "digest": p.MODEL_DIGEST}]}))
        self.assertEqual(self.client.inventory(), p.MODEL)
    def chat(self, role="target", response=None):
        self.opener.responses.append(Response(envelope()) if response is None else response)
        return self.client.chat(role, MESSAGES, format_schema=p.RESPONSE_SCHEMA if role == "attacker" else None)

    def test_transport_has_no_proxy_or_redirect_and_only_fixed_paths(self):
        handlers = self.start.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], c.NoRedirect)
        with self.assertRaises(ValueError):
            handlers[1].redirect_request(None, None, 302, "redirect", {}, "https://example.invalid")
        with self.assertRaises(ValueError): self.client._request("/api/pull")
        self.assertEqual(self.opener.calls, [])

    def test_model_inventory_is_required_and_exact_before_role_calls(self):
        with self.assertRaises(ValueError): self.client.chat("target", MESSAGES)
        self.assertEqual(self.client.counters, {"attacker": 0, "target": 0})
        self.assertEqual(self.opener.calls, [])
        self.bind()
        self.assertEqual(self.opener.calls[0][0].full_url, c.BASE + "/api/tags")
        self.assertIsNone(self.opener.calls[0][0].data)

    def test_inventory_missing_duplicate_changed_or_unbounded_model_is_rejected(self):
        for data in ({}, {"models": None}, {"models": []},
                     {"models": [{"name": p.MODEL_NAME, "digest": "a" * 64}]},
                     {"models": [{"name": p.MODEL_NAME, "digest": p.MODEL_DIGEST}] * 2},
                     {"models": [{}] * 129}):
            with self.subTest(data=data):
                client = c.AdaptiveLoopbackClient()
                self.opener.responses.append(Response(data))
                with self.assertRaises(ValueError): client.inventory()
                with self.assertRaises(ValueError): client.chat("target", MESSAGES)

    def test_only_two_inventory_attempts_are_available(self):
        self.bind(); self.bind()
        before = len(self.opener.calls)
        with self.assertRaises(ValueError): self.client.inventory()
        self.assertEqual(len(self.opener.calls), before)
        self.assertEqual(self.client.inventory_calls, 2)
        with self.assertRaises(ValueError): self.client.chat("target", MESSAGES)

    def test_changed_post_inventory_prevents_more_role_calls(self):
        self.bind()
        self.opener.responses.append(Response({"models": [{"name": p.MODEL_NAME, "digest": "b" * 64}]}))
        with self.assertRaises(ValueError): self.client.inventory()
        with self.assertRaises(ValueError): self.client.chat("target", MESSAGES)

    def test_failed_post_inventory_invalidates_previous_binding(self):
        for failure in (Response({}), TimeoutError("Synthetic inventory failure")):
            with self.subTest(failure=type(failure).__name__):
                self.client = c.AdaptiveLoopbackClient()
                self.bind()
                self.opener.responses.append(failure)
                with self.assertRaises((ValueError, TimeoutError)): self.client.inventory()
                before = len(self.opener.calls)
                with self.assertRaises(ValueError): self.client.chat("target", MESSAGES)
                self.assertEqual(len(self.opener.calls), before)
                self.assertEqual(self.client.counters, {"attacker": 0, "target": 0})

    def test_attacker_and_target_payloads_are_separate_and_copied(self):
        self.bind()
        self.chat("attacker"); self.chat("target")
        attacker, target = [json.loads(row[0].data) for row in self.opener.calls[1:]]
        self.assertEqual(attacker["format"], p.RESPONSE_SCHEMA)
        self.assertEqual(attacker["options"], p.ATTACKER_OPTIONS)
        self.assertEqual(attacker["options"]["num_predict"], 512)
        self.assertEqual(target["options"], p.TARGET_OPTIONS)
        self.assertEqual(target["options"]["num_predict"], 256)
        self.assertNotIn("format", target)
        self.assertFalse(attacker["stream"])
        self.assertEqual(attacker["model"], target["model"])
        self.assertEqual(self.client.counters, {"attacker": 1, "target": 1})
        records = self.client.requests
        records[0]["payload"]["options"]["num_predict"] = 999
        self.assertEqual(self.client.requests[0]["payload"]["options"]["num_predict"], 512)

    def test_invalid_roles_messages_or_schema_never_spend_a_call(self):
        self.bind()
        for role in (True, None, "judge", "Attacker", ""):
            with self.subTest(role=role), self.assertRaises(ValueError): self.client.chat(role, MESSAGES)
        bad_messages = [None, [], MESSAGES[:1], [{"role": "user", "content": "wrong first role"}, MESSAGES[1]],
            [MESSAGES[0], {"role": "assistant", "content": "wrong last role"}],
            [MESSAGES[0], {"role": "user", "content": True}],
            [MESSAGES[0], {"role": "user", "content": " "}],
            [MESSAGES[0], {"role": "user", "content": "x" * (p.MAX_TEXT + 1)}],
            [MESSAGES[0], {**MESSAGES[1], "tool_calls": []}],
            MESSAGES * 4]
        for value in bad_messages:
            with self.subTest(messages=value), self.assertRaises(ValueError): self.client.chat("target", value)
        for role, schema in (("attacker", None), ("attacker", {}), ("target", p.RESPONSE_SCHEMA)):
            with self.subTest(role=role), self.assertRaises(ValueError): self.client.chat(role, MESSAGES, format_schema=schema)
        changed = copy.deepcopy(p.RESPONSE_SCHEMA); changed["additionalProperties"] = 0
        with self.assertRaises(ValueError): self.client.chat("attacker", MESSAGES, format_schema=changed)
        self.assertEqual(self.client.counters, {"attacker": 0, "target": 0})
        self.assertEqual(len(self.opener.calls), 1)

    def test_history_total_is_bounded_before_dispatch(self):
        messages = [{"role": "system" if index == 0 else "user" if index % 2 else "assistant", "content": "x" * p.MAX_TEXT} for index in range(6)]
        with self.assertRaises(ValueError): c.build_payload("target", messages)
        self.assertEqual(self.opener.calls, [])

    def test_each_role_six_and_combined_twelve_calls_never_retry(self):
        self.bind()
        for _ in range(6): self.chat("attacker"); self.chat("target")
        self.assertEqual(self.client.counters, {"attacker": 6, "target": 6})
        self.assertEqual(len(self.opener.calls), 13)
        for role in ("attacker", "target"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                self.client.chat(role, MESSAGES, format_schema=p.RESPONSE_SCHEMA if role == "attacker" else None)
        self.assertEqual(len(self.opener.calls), 13)
        copied = self.client.counters; copied["attacker"] = 0
        self.assertEqual(self.client.counters["attacker"], 6)

    def test_transport_error_consumes_one_attempt_and_retains_role_payload(self):
        self.bind()
        self.opener.responses.append(TimeoutError("Synthetic transport failure"))
        with self.assertRaises(TimeoutError): self.client.chat("attacker", MESSAGES, format_schema=p.RESPONSE_SCHEMA)
        self.assertEqual(self.client.counters, {"attacker": 1, "target": 0})
        self.assertEqual(len(self.opener.calls), 2)
        record = self.client.requests[0]
        self.assertEqual(record["role"], "attacker")
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error_type"], "TimeoutError")
        self.assertEqual(record["payload"]["format"], p.RESPONSE_SCHEMA)

    def test_deadline_refuses_new_io_and_detects_elapsed_response(self):
        self.bind()
        with mock.patch.object(c.time, "monotonic", return_value=self.client.deadline + 1):
            with self.assertRaises(TimeoutError): self.client.chat("target", MESSAGES)
        self.assertEqual(len(self.opener.calls), 1)
        self.assertEqual(self.client.counters["target"], 1)
        self.opener.responses.append(Response(envelope()))
        with mock.patch.object(c.time, "monotonic", side_effect=[self.client.deadline - 3, self.client.deadline + 1]):
            with self.assertRaises(TimeoutError): self.client.chat("target", MESSAGES)
        self.assertEqual(self.opener.calls[-1][1], 3)

    def test_exact_json_mime_allows_parameters_but_rejects_prefix_lookalikes(self):
        self.bind()
        self.assertEqual(self.chat("target", Response(envelope(), content_type=" Application/JSON ; charset=utf-8")), envelope())
        for mime in ("text/html", "application/json-foo", "application/jsonp", "application/json extra", ""):
            self.opener.responses.append(Response(envelope(), content_type=mime))
            with self.subTest(mime=mime), self.assertRaises(ValueError): self.client.chat("target", MESSAGES)

    def test_provider_bytes_content_type_status_and_strict_json_are_bounded(self):
        self.bind()
        failures = [Response({}, raw=b"x" * (p.MAX_PROVIDER_BYTES + 1)), Response({}, content_type="application/json-foo"),
                    Response({}, status=201), Response({}, raw=b'{"x":1,"x":1}'), Response({}, raw=b'{"x":NaN}')]
        for response in failures:
            with self.subTest(response=response), self.assertRaises((ValueError, UnicodeError)):
                self.chat("target", response)
        self.assertTrue(all(self.client.requests[index]["status"] == "error" for index in range(5)))
        self.assertEqual(self.client.counters["target"], 5)

    def test_truncated_raw_marker_envelope_remains_unmodified_and_unusable(self):
        self.bind()
        raw = envelope(p.MARKER); raw.update(done=False, done_reason="length")
        observed = self.chat("attacker", Response(raw))
        self.assertEqual(observed, raw)
        normalized = p.normalize_attacker_response(observed)
        self.assertEqual(normalized["status"], "unusable")
        self.assertIsNone(normalized["reply"])
        self.assertTrue(normalized["observed_literal_hit"])
        self.assertEqual(normalized["text"], p.MARKER)

    def test_wrong_response_model_role_and_tool_request_are_not_repaired(self):
        self.bind()
        for key in ("model", "role", "tool"):
            raw = envelope(p.MARKER)
            if key == "model": raw["model"] = "other-model"
            elif key == "role": raw["message"]["role"] = "user"
            else: raw["message"]["tool_calls"] = [{"function": {"name": "inert", "arguments": {}}}]
            with self.subTest(binding=key):
                returned = self.chat("attacker", Response(raw))
                self.assertEqual(returned, raw)
                self.assertEqual(p.normalize_attacker_response(returned)["status"], "unusable")
                self.assertTrue(p.normalize_attacker_response(returned)["observed_literal_hit"])


if __name__ == "__main__": unittest.main()
