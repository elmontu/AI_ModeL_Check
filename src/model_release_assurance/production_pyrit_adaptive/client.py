"""Bounded role-specific local Ollama transport for public adaptive fixtures."""
from __future__ import annotations
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from ..production_adapters.contracts import canonical_bytes, strict_json
from . import protocol as p

BASE = "http://127.0.0.1:11434"
ROLES = ("attacker", "target")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("The fixed adaptive loopback target redirected a request")


def build_payload(role, messages, *, format_schema=None):
    """Validate and copy the exact wire request without spending a role call."""
    if type(role) is not str or role not in ROLES:
        raise ValueError("Only the fixed attacker and target roles are supported")
    if type(messages) is not list or not 2 <= len(messages) <= p.BOUNDS["max_history_messages"]:
        raise ValueError("A bounded system and user history is required")
    characters = 0
    for index, message in enumerate(messages):
        if type(message) is not dict or set(message) != {"role", "content"}:
            raise ValueError("Only exact text message fields are supported")
        expected_role = "system" if index == 0 else "user" if index % 2 else "assistant"
        if message["role"] != expected_role or type(message["content"]) is not str:
            raise ValueError("The fixed message role order changed")
        if not message["content"].strip() or len(message["content"]) > p.MAX_TEXT:
            raise ValueError("Message text is empty or exceeds its bound")
        characters += len(message["content"])
    if messages[-1]["role"] != "user" or characters > p.BOUNDS["max_history_characters"]:
        raise ValueError("The final request or history text bound changed")
    options = p.ATTACKER_OPTIONS if role == "attacker" else p.TARGET_OPTIONS
    payload = {"model": p.MODEL_NAME, "messages": p.owned(messages), "stream": False, "options": dict(options)}
    if role == "attacker":
        if format_schema is None:
            raise ValueError("The attacker requires the declared upstream JSON schema")
        p.validate_schema(format_schema)
        payload["format"] = p.owned(format_schema)
    elif format_schema is not None:
        raise ValueError("Target requests cannot acquire an attacker response schema")
    return payload


class AdaptiveLoopbackClient:
    """At most six requests per role and twelve combined; no transport retry.

    Socket inactivity and between-request checks do not bound server execution.
    The separate Ollama service is outside the owned worker's process group.
    """
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.deadline = time.monotonic() + p.BOUNDS["campaign_deadline_seconds"]
        self._counters = {role: 0 for role in ROLES}
        self._inventory_calls = 0
        self._requests = []
        self._model_bound = False

    @property
    def counters(self):
        return dict(self._counters)

    @property
    def inventory_calls(self):
        return self._inventory_calls

    @property
    def requests(self):
        return p.owned(self._requests)

    def _request(self, path, payload=None):
        if path not in ("/api/tags", "/api/chat"):
            raise ValueError("Unsupported adaptive fixture endpoint")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The declared adaptive campaign deadline elapsed")
        request = Request(BASE + path, data=None if payload is None else canonical_bytes(payload),
            headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=min(p.BOUNDS["request_timeout_seconds"], remaining)) as response:
            if getattr(response, "status", 200) != 200:
                raise ValueError("Unsupported adaptive provider status")
            raw = response.read(p.MAX_PROVIDER_BYTES + 1)
            if len(raw) > p.MAX_PROVIDER_BYTES:
                raise ValueError("Adaptive provider byte bound exceeded")
            content_type = response.headers.get("Content-Type", "")
            if type(content_type) is not str or content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("Unsupported adaptive provider content type")
        if time.monotonic() > self.deadline:
            raise TimeoutError("The adaptive deadline elapsed during a request")
        return strict_json(raw, maximum=p.MAX_PROVIDER_BYTES)

    def inventory(self):
        self._model_bound = False
        if self._inventory_calls >= 2:
            raise ValueError("Only the fixed pre/post inventory queries are supported")
        self._inventory_calls += 1
        data = self._request("/api/tags")
        if type(data) is not dict or type(data.get("models")) is not list or len(data["models"]) > 128:
            raise ValueError("A bounded adaptive model inventory is required")
        matches = [row for row in data["models"] if type(row) is dict and row.get("name") == p.MODEL_NAME]
        if len(matches) != 1 or matches[0].get("digest") != p.MODEL_DIGEST:
            self._model_bound = False
            raise ValueError("The shared attacker/target model digest is unavailable or changed")
        self._model_bound = True
        return dict(p.MODEL)

    def chat(self, role, messages, *, format_schema=None):
        payload = build_payload(role, messages, format_schema=format_schema)
        if not self._model_bound:
            raise ValueError("The shared model inventory must be bound before role requests")
        limit = p.BOUNDS["attacker_calls"] if role == "attacker" else p.BOUNDS["target_calls"]
        if self._counters[role] >= limit or sum(self._counters.values()) >= p.BOUNDS["total_live_calls"]:
            raise ValueError("The adaptive role or combined call bound is exhausted")
        self._counters[role] += 1
        record = {"role": role, "role_call": self._counters[role], "payload": payload}
        self._requests.append(record)
        try:
            response = self._request("/api/chat", payload)
            record["status"] = "completed"
            return response
        except Exception as error:
            record.update(status="error", error_type=type(error).__name__)
            raise
