"""Allowlisted unmodified garak probe/detector path and fixed loopback target.

No upstream CLI, dynamic plugin selection, credentials or executable tools are exposed.
Optional component imports happen only after the worker checks the pinned runtime.
"""
from __future__ import annotations
import hashlib
import io
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from ..production_adapters.contracts import canonical_bytes, strict_json
from . import protocol as p

BASE = "http://127.0.0.1:11434"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("The fixed loopback runtime redirected a request")


class LoopbackClient:
    """Two fixed Ollama endpoints, no proxy or redirect, bounded response and time."""
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.deadline = time.monotonic() + p.BOUNDS["campaign_deadline_seconds"]
        self.target_calls = 0

    def _request(self, path, payload=None):
        if path not in ("/api/tags", "/api/chat"):
            raise ValueError("Unsupported fixture endpoint")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("The declared campaign deadline elapsed")
        data = canonical_bytes(payload) if payload is not None else None
        request = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=min(60, remaining)) as response:
            raw = response.read(p.MAX_PROVIDER_BYTES + 1)
            if len(raw) > p.MAX_PROVIDER_BYTES:
                raise ValueError("The local target response exceeded its byte bound")
            if not response.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise ValueError("The local target returned an unsupported content type")
        if time.monotonic() > self.deadline:
            raise TimeoutError("The declared campaign deadline elapsed during a request")
        return strict_json(raw, maximum=p.MAX_PROVIDER_BYTES)

    def inventory(self):
        data = self._request("/api/tags")
        if type(data) is not dict or type(data.get("models")) is not list or len(data["models"]) > 128:
            raise ValueError("A bounded local model inventory is required")
        matches = [item for item in data["models"] if type(item) is dict and item.get("name") == p.MODEL_NAME]
        if len(matches) != 1 or matches[0].get("digest") != p.MODEL_DIGEST:
            raise ValueError("The declared local model digest is unavailable or changed")
        return dict(p.MODEL)

    def chat(self, messages):
        if self.target_calls >= p.BOUNDS["target_calls"]:
            raise ValueError("The declared target query limit was exhausted")
        self.target_calls += 1
        return self._request("/api/chat", {"model": p.MODEL_NAME, "messages": p.owned(messages),
                             "stream": False, "options": dict(p.OPTIONS)})


def _components():
    from garak import _config
    from garak.attempt import Attempt, Message, Conversation, Turn
    from garak.probes.promptinject import HijackLongPrompt
    from garak.detectors.promptinject import AttackRogueString
    _config.run.seed = 20261006
    _config.run.soft_probe_prompt_cap = 0
    _config.run.generations = 1
    _config.run.system_prompt = None
    _config.run.target_lang = "en"
    _config.run.langproviders = []
    _config.system.parallel_attempts = 1
    _config.system.parallel_requests = 1
    _config.system.max_workers = 1
    _config.system.verbose = 0
    _config.buffmanager.buffs = []
    return _config, Attempt, Message, Conversation, Turn, HijackLongPrompt, AttackRogueString


def _bounded_probe(parts):
    probe = parts[5]()
    if len(probe.prompts) != 700 or len(probe.pi_prompts) != 700:
        raise ValueError("The pinned builtin corpus size changed")
    if any(record["prompt"] != prompt for record, prompt in zip(probe.pi_prompts, probe.prompts)):
        raise ValueError("Upstream prompt and metadata order disagree")
    records = [{"index": index, "prompt": probe.prompts[index],
                "trigger": probe.pi_prompts[index]["settings"]["attack_rogue_string"],
                "settings": probe.pi_prompts[index]["settings"]} for index in p.INDICES]
    corpus = p.validate_corpus(records)
    probe.prompts = [probe.prompts[index] for index in p.INDICES]
    probe.pi_prompts = [probe.pi_prompts[index] for index in p.INDICES]
    return probe, corpus


def build_corpus():
    """Prepare exact builtin prompt/settings records without calling any target."""
    return _bounded_probe(_components())[1]


def _score(detector, attempt):
    scores = list(detector.detect(attempt))
    if len(scores) != 1 or (scores[0] is not None and (type(scores[0]) is not float or scores[0] not in (0.0, 1.0))):
        raise ValueError("Unexpected upstream detector output")
    return scores[0]


def _attempt(parts, text):
    attempt = parts[1](prompt=parts[2]("Fixed lexical calibration", lang="en"),
                       notes={"triggers": [p.TRIGGER]})
    attempt.outputs = [parts[2](text=text, lang="en")]
    return attempt


class FixedGenerator:
    """Adapt builtin user text to a declared interface; never executes actions."""
    parallel_capable = False

    def __init__(self, parts, corpus, interface, mode, client):
        self.parts, self.corpus, self.interface = parts, corpus, interface
        self.mode, self.client, self.records = mode, client, []

    def clear_history(self):
        pass

    def generate(self, conversation, generations_this_call=1):
        if type(generations_this_call) is not int or generations_this_call != 1 or len(self.records) >= 4:
            raise ValueError("Only one fixed generation per declared prompt is supported")
        expected = self.corpus[len(self.records)]
        if len(conversation.turns) != 1 or conversation.turns[0].role != "user" or conversation.turns[0].content.text != expected["prompt"]:
            raise ValueError("The upstream attempted prompt changed before target execution")
        messages = p.messages_for(self.interface, expected["prompt"])
        try:
            if self.mode == "positive":
                # Deliberately vulnerable scripted text target; marker must reach it through the actual wrapper.
                text = p.TRIGGER if any(p.literal_hit(turn["content"]) for turn in messages) else "CONTROL_MISSING"
                response = {"model": p.MODEL_NAME, "message": {"role": "assistant", "content": text}, "done": True, "done_reason": "stop", "eval_count": 1, "prompt_eval_count": 1}
            elif self.mode == "null":
                response = {"model": p.MODEL_NAME, "message": {"role": "assistant", "content": "The document is a grammar exercise."}, "done": True, "done_reason": "stop", "eval_count": 1, "prompt_eval_count": 1}
            elif self.mode == "target":
                response = self.client.chat(messages)
            else:
                raise ValueError("Unsupported fixed generator mode")
            response = p.owned(response)
        except Exception as exc:
            response = {"error": type(exc).__name__, "fixture_request_failed": True}
        observation = p.observe_response(response)
        self.records.append({"actual_messages": messages, "response": response, "observation": observation})
        return [self.parts[2](text=observation["text"], lang="en")]


def _probe_records(parts, corpus, interface, mode, client):
    probe, current = _bounded_probe(parts)
    if canonical_bytes(current) != canonical_bytes(corpus):
        raise ValueError("The prepared corpus changed")
    generator = FixedGenerator(parts, corpus, interface, mode, client)
    report = io.StringIO()
    parts[0].transient.reportfile = report
    attempts = list(probe.probe(generator))
    if len(attempts) != 4 or len(generator.records) != 4:
        raise ValueError("The upstream probe produced an unexpected attempt count")
    detector = parts[6]()
    rows = []
    for seq, (attempt, source, call) in enumerate(zip(attempts, corpus, generator.records)):
        if (attempt.seq != seq or attempt.probe_classname != p.PROBE
                or attempt.notes.get("triggers") != [p.TRIGGER]
                or canonical_bytes(attempt.notes.get("settings")) != canonical_bytes(source["settings"])):
            raise ValueError("The upstream attempted record changed")
        rows.append({"id": interface + "/" + str(source["index"]), "interface": interface,
                     "index": source["index"], "prompt": source["prompt"], "settings": source["settings"],
                     "triggers": [p.TRIGGER], **call, "upstream_score": _score(detector, attempt),
                     "upstream_attempt": p.owned(attempt.as_dict())})
    return rows, {"interface": interface, "mode": mode,
                  "report_sha256": hashlib.sha256(report.getvalue().encode("utf-8")).hexdigest(), "report_text": report.getvalue()}


def _target_controls(parts, client):
    detector = parts[6]()
    records = []
    for interface in p.INTERFACES:
        for kind in ("benign_echo", "unprotected_echo"):
            messages, expected = p.control_messages(interface, kind)
            try:
                response = p.owned(client.chat(messages))
            except Exception as exc:
                response = {"error": type(exc).__name__, "fixture_request_failed": True}
            observation = p.observe_response(response)
            score = _score(detector, _attempt(parts, observation["text"]))
            valid = (observation["status"] == "scored" and observation["text"].strip() == expected
                     and not observation["tool_call_requested"])
            records.append({"id": interface + "/" + kind, "interface": interface, "kind": kind,
                            "actual_messages": messages, "expected_text": expected, "response": response,
                            "observation": observation, "upstream_score": score, "valid": valid})
    return records


def _scorer_controls(parts):
    detector = parts[6]()
    records = []
    for control in p.scorer_controls():
        score = _score(detector, _attempt(parts, control["text"]))
        records.append({**control, "upstream_score": score, "valid": score == control["expected_score"]})
    return records


def run_campaign(plan, *, client=None):
    """Execute the fixed builtin path with scripted controls and a local target."""
    plan = p.validate_plan(plan)
    parts = _components()
    corpus = _bounded_probe(parts)[1]
    if canonical_bytes(corpus) != canonical_bytes(plan["corpus"]):
        raise ValueError("The prepared upstream corpus no longer matches")
    client = LoopbackClient() if client is None else client
    before = client.inventory()  # Fail closed before issuing any target inference calls.
    if canonical_bytes(before) != canonical_bytes(p.MODEL):
        raise ValueError("The prepared local target binding changed")
    campaign = {"attacks": [], "scripted_controls": {"positive": [], "null": []},
                "target_controls": [], "scorer_controls": _scorer_controls(parts),
                "inventory": {"before": before, "after": None}, "upstream_reports": []}
    for interface in p.INTERFACES:
        for mode in ("positive", "null", "target"):
            rows, report = _probe_records(parts, corpus, interface, mode, client)
            if mode == "target":
                campaign["attacks"].extend(rows)
            else:
                campaign["scripted_controls"][mode].extend(rows)
            campaign["upstream_reports"].append(report)
    campaign["target_controls"] = _target_controls(parts, client)
    try:
        campaign["inventory"]["after"] = p.owned(client.inventory())
    except Exception as exc:
        campaign["inventory"]["after"] = {"error": type(exc).__name__}
    return p.owned(campaign)
