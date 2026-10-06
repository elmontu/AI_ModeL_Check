"""Unmodified PyRIT attack loop with declared local targets and inert evidence.

The only runtime hook redirects the two known appdirs PyRIT storage calls.
It does not provide host, network, filesystem or server isolation.
"""
from __future__ import annotations
import asyncio
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import time
import uuid
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from ..production_adapters import native
from ..production_adapters.contracts import canonical_bytes, strict_json
from . import protocol as p

BASE = "http://127.0.0.1:11434"
_COMPONENTS = None
_PATH_BINDING = None

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("The fixed loopback target redirected a request")

class LoopbackClient:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.deadline = time.monotonic() + p.BOUNDS["campaign_deadline_seconds"]
        self.target_calls = 0

    def _request(self, path, payload=None):
        if path not in ("/api/tags", "/api/chat"): raise ValueError("Unsupported fixture endpoint")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError("The declared campaign deadline elapsed")
        request = Request(BASE + path, data=None if payload is None else canonical_bytes(payload), headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=min(60, remaining)) as response:
            raw = response.read(p.MAX_PROVIDER_BYTES + 1)
            if len(raw) > p.MAX_PROVIDER_BYTES: raise ValueError("Provider byte bound exceeded")
            if not response.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise ValueError("Unsupported provider content type")
        if time.monotonic() > self.deadline: raise TimeoutError("The campaign deadline elapsed during a request")
        return strict_json(raw, maximum=p.MAX_PROVIDER_BYTES)

    def inventory(self):
        data = self._request("/api/tags")
        if type(data) is not dict or type(data.get("models")) is not list or len(data["models"]) > 128:
            raise ValueError("A bounded model inventory is required")
        matches = [item for item in data["models"] if type(item) is dict and item.get("name") == p.MODEL_NAME]
        if len(matches) != 1 or matches[0].get("digest") != p.MODEL_DIGEST:
            raise ValueError("The fixed model digest is unavailable or changed")
        return dict(p.MODEL)

    def chat(self, messages):
        if self.target_calls >= p.BOUNDS["target_calls"]: raise ValueError("Target call bound exhausted")
        self.target_calls += 1
        if type(messages) is not list or len(messages) > p.BOUNDS["max_history_messages"]:
            raise ValueError("History count bound exceeded")
        if sum(len(item["content"]) for item in messages) > p.BOUNDS["max_history_characters"]:
            raise ValueError("History text bound exceeded")
        return self._request("/api/chat", {"model": p.MODEL_NAME, "messages": p.owned(messages), "stream": False, "options": dict(p.OPTIONS)})


def _install_storage_hook():
    global _PATH_BINDING
    if _PATH_BINDING is not None:
        return check_paths()
    if any(name == "pyrit" or name.startswith("pyrit.") for name in sys.modules):
        raise ValueError("PyRIT must not be preloaded before owned storage routing")
    root = Path(os.environ.get("LOCALAPPDATA", "")).absolute()
    binding = {"schema": "mra-pyrit-cache-binding/v1", "root": str(root),
        "db_data_path": str(root / "pyrit/dbdata"), "cache_path": str(root / "pyrit/.pyrit_cache"),
        "log_path": str(root / "pyrit/dbdata/logs.txt"), "hook": "trusted_fixed_appdirs_pyrit/v1", "profile_discovery": False}
    p.validate_cache_binding(binding, expected_root=root); native._real_directory(root)
    if Path.home().absolute() != root: raise ValueError("PyRIT home must be the owned cache")
    for name in ("HOME", "USERPROFILE", "APPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        if Path(os.environ.get(name, "")).absolute() != root: raise ValueError("PyRIT environment cache routing changed")
    if any(os.environ.get(name) != "1" for name in ("RETRY_MAX_NUM_ATTEMPTS", "CUSTOM_RESULT_RETRY_MAX_NUM_ATTEMPTS")):
        raise ValueError("PyRIT retries must be bounded before imports")
    spec = importlib.util.find_spec("pyrit")
    if spec is None or not spec.origin: raise ValueError("The pinned PyRIT path is unavailable")
    # Upstream bypasses appdirs when its installed site-packages has a .git marker.
    if os.path.lexists(Path(spec.origin).parent.parent / ".git"):
        raise ValueError("The installed runtime cannot use repository-based storage")
    import appdirs
    def fixed_user_data_dir(appname=None, appauthor=None, version=None, roaming=False):
        if appauthor != "pyrit" or appname not in ("dbdata", ".pyrit_cache") or version is not None or roaming is not False:
            raise ValueError("Undeclared appdirs storage request")
        return str(root / "pyrit" / appname)
    appdirs.user_data_dir = fixed_user_data_dir
    _PATH_BINDING = binding
    return binding


def check_paths():
    if _PATH_BINDING is None: raise ValueError("Owned PyRIT storage is not installed")
    module = sys.modules.get("pyrit.common.path")
    if module is not None:
        for name, key in (("DB_DATA_PATH", "db_data_path"), ("PYRIT_CACHE_PATH", "cache_path"), ("LOG_PATH", "log_path")):
            if Path(getattr(module, name)).absolute() != Path(_PATH_BINDING[key]):
                raise ValueError("PyRIT created an undeclared cache path")
        native._real_directory(Path(_PATH_BINDING["db_data_path"]))
        native._real_directory(Path(_PATH_BINDING["cache_path"]))
        from .runtime import _file
        _file(Path(_PATH_BINDING["log_path"]), p.MAX_BYTES)
    return p.validate_cache_binding(_PATH_BINDING, expected_root=Path(os.environ["LOCALAPPDATA"]))


def _history(conversation):
    if not 1 <= len(conversation) <= p.BOUNDS["max_history_messages"]: raise ValueError("Upstream history count bound exceeded")
    result = []
    for message in conversation:
        if len(message.message_pieces) != 1: raise ValueError("Only single text pieces are supported")
        piece = message.get_piece()
        if piece.original_value != piece.converted_value or piece.original_value_data_type != "text" or piece.converted_value_data_type != "text":
            raise ValueError("Undeclared conversion or modality")
        if len(piece.converted_value) > p.MAX_TEXT: raise ValueError("Upstream text bound exceeded")
        result.append({"role": piece.role, "text": piece.converted_value})
    if sum(len(row["text"]) for row in result) > p.BOUNDS["max_history_characters"]: raise ValueError("History text bound exceeded")
    return result


def _components():
    global _COMPONENTS
    if _COMPONENTS is not None:
        check_paths(); return _COMPONENTS
    _install_storage_hook()
    from pyrit.memory import CentralMemory, SQLiteMemory
    from pyrit.prompt_target import PromptTarget, TargetCapabilities, TargetConfiguration
    from pyrit.models import Message, MessagePiece, ScoringExpectation, AtomicAttackIdentifier
    from pyrit.models.identifiers.evaluation_identifier import AtomicAttackEvaluationIdentifier
    from pyrit.executor.attack import RedTeamingAttack, AttackAdversarialConfig, AttackScoringConfig
    from pyrit.prompt_normalizer import PromptNormalizer
    from pyrit.score import SubStringScorer, MessageScorable
    from pyrit.analytics.text_matching import ExactTextMatching

    class FixedScriptedAttacker(PromptTarget):
        _DEFAULT_CONFIGURATION = TargetConfiguration(capabilities=TargetCapabilities(supports_multi_turn=True, supports_editable_history=True,
            supports_system_prompt=True, supports_json_output=True, supports_json_schema=True))
        def __init__(self, *, case_id, mode):
            self.case_id, self.mode, self.records = case_id, mode, []
            super().__init__(model_name="fixed-public-scripted-attacker/v1")
        def _build_identifier(self):
            return self._create_identifier(params={"case_id": self.case_id, "mode": self.mode,
                "script_sha256": p.sha([p.attacker_reply(self.case_id, turn) for turn in range(1, 4)])})
        async def _send_prompt_to_target_async(self, *, normalized_conversation):
            history = _history(normalized_conversation); turn = len(self.records) + 1
            if turn > 3: raise ValueError("Attacker call bound exceeded")
            reply = p.attacker_reply(self.case_id, turn)
            response = Message.from_prompt(prompt=canonical_bytes(reply).decode("utf-8"), role="assistant")
            request = normalized_conversation[-1].get_piece()
            self.records.append({"turn": turn, "conversation_id": request.conversation_id, "history": history,
                "request_id": str(request.id), "response_id": str(response.get_piece().id), "reply": reply})
            return [response]

    class FixedObjectiveTarget(PromptTarget):
        _DEFAULT_CONFIGURATION = TargetConfiguration(capabilities=TargetCapabilities(supports_multi_turn=True,
            supports_editable_history=True, supports_system_prompt=True))
        def __init__(self, *, case_id, mode, client=None):
            self.case_id, self.mode, self.client, self.records, self.reset_ids = case_id, mode, client, [], []
            super().__init__(model_name=p.MODEL_NAME if mode == "target" else "fixed-public-" + mode + "/v1", endpoint=BASE if mode == "target" else "")
        def _build_identifier(self):
            return self._create_identifier(params={"case_id": self.case_id, "mode": self.mode, "model_digest": p.MODEL_DIGEST,
                "system_sha256": p.text_sha(p.TARGET_SYSTEM), "options": dict(p.OPTIONS), "inert_tools": True})
        async def reset_conversation_async(self, *, conversation_id):
            self.reset_ids.append(conversation_id)
        async def _send_prompt_to_target_async(self, *, normalized_conversation):
            history = _history(normalized_conversation); turn = len(self.records) + 1
            if turn > 3: raise ValueError("Objective call bound exceeded")
            messages = [{"role": "system", "content": p.TARGET_SYSTEM}] + [{"role": row["role"], "content": row["text"]} for row in history]
            try:
                if self.mode == "target": raw = self.client.chat(messages)
                else: raw = {"model": p.MODEL_NAME, "message": {"role": "assistant", "content": p.control_text(self.mode, turn)},
                    "done": True, "done_reason": "stop", "eval_count": 1, "prompt_eval_count": 1}
                raw = p.owned(raw)
            except Exception as exc:
                raw = {"error": type(exc).__name__, "fixture_request_failed": True}
            observation = p.observe_response(raw)
            response = Message(message_pieces=[MessagePiece(role="assistant", original_value=observation["text"] or "",
                response_error="none" if observation["status"] == "scored" else "processing")])
            request = normalized_conversation[-1].get_piece()
            self.records.append({"turn": turn, "conversation_id": request.conversation_id, "history": history,
                "actual_messages": messages, "request_id": str(request.id), "response_id": str(response.get_piece().id), "response": raw, "observation": observation})
            return [response]

    for cls in (FixedScriptedAttacker, FixedObjectiveTarget):
        cls.__module__ = __name__; cls.__qualname__ = cls.__name__
    _COMPONENTS = dict(CentralMemory=CentralMemory, SQLiteMemory=SQLiteMemory, Message=Message, MessagePiece=MessagePiece,
        ScoringExpectation=ScoringExpectation, AtomicAttackIdentifier=AtomicAttackIdentifier, AtomicAttackEvaluationIdentifier=AtomicAttackEvaluationIdentifier, RedTeamingAttack=RedTeamingAttack,
        AttackAdversarialConfig=AttackAdversarialConfig, AttackScoringConfig=AttackScoringConfig, PromptNormalizer=PromptNormalizer,
        SubStringScorer=SubStringScorer, MessageScorable=MessageScorable, ExactTextMatching=ExactTextMatching,
        FixedScriptedAttacker=FixedScriptedAttacker, FixedObjectiveTarget=FixedObjectiveTarget)
    check_paths(); return _COMPONENTS


def _memory(parts):
    memory = parts["SQLiteMemory"](db_path=":memory:", silent=True)
    parts["CentralMemory"].set_memory_instance(memory)
    memory.reset_database()
    if memory.get_message_pieces() or memory.get_scores(score_type="true_false"): raise ValueError("PyRIT memory did not reset")
    return memory


def _assembly(parts, case_id, mode, client=None):
    target = parts["FixedObjectiveTarget"](case_id=case_id, mode=mode, client=client)
    attacker = parts["FixedScriptedAttacker"](case_id=case_id, mode=mode)
    scorer = parts["SubStringScorer"](substring=p.MARKER,
        text_matcher=parts["ExactTextMatching"](case_sensitive=True, ignore_whitespace=False))
    attack = parts["RedTeamingAttack"](objective_target=target,
        attack_adversarial_config=parts["AttackAdversarialConfig"](target=attacker,
            system_prompt=p.ATTACKER_SYSTEM_TEMPLATE, first_message=p.FIRST_TEMPLATE, adversarial_prompt_template=p.NEXT_TEMPLATE),
        attack_scoring_config=parts["AttackScoringConfig"](objective_scorer=scorer, use_score_as_feedback=False),
        prompt_normalizer=parts["PromptNormalizer"](), max_turns=3, score_last_turn_only=False)
    atomic = parts["AtomicAttackIdentifier"].build(attack_identifier=attack.get_identifier())
    atomic = atomic.with_eval_hash(parts["AtomicAttackEvaluationIdentifier"](atomic).eval_hash)
    identity = {"case_id": case_id, "mode": mode, "objective_target": target.get_identifier().model_dump(mode="json"),
        "adversarial_chat": attacker.get_identifier().model_dump(mode="json"), "objective_scorer": scorer.get_identifier().model_dump(mode="json"),
        "attack": attack.get_identifier().model_dump(mode="json"),
        "atomic_attack": atomic.model_dump(mode="json")}
    return target, attacker, scorer, attack, p.owned(identity)


def build_identifiers():
    """Construct official identities without invoking attacker or objective targets."""
    parts = _components(); memory = _memory(parts)
    identities = [_assembly(parts, case_id, mode)[4] for case_id in p.INTERFACES for mode in p.MODES]
    if memory.get_message_pieces() or memory.get_scores(score_type="true_false"): raise ValueError("Preparation invoked a target")
    return p.validate_identifiers(identities)


def _message_rows(memory, conversation_id):
    result = []
    for piece in memory.get_message_pieces(conversation_id=conversation_id):
        if piece.original_value_data_type != "text" or piece.converted_value_data_type != "text" or piece.converter_identifiers:
            raise ValueError("Undeclared memory conversion or modality")
        result.append({"id": str(piece.id), "role": piece.role, "text": piece.converted_value, "original_text": piece.original_value,
            "conversation_id": piece.conversation_id, "sequence": piece.sequence,
            "original_sha256": piece.original_value_sha256, "converted_sha256": piece.converted_value_sha256,
            "recomputed_original_sha256": p.text_sha(piece.original_value), "recomputed_converted_sha256": p.text_sha(piece.converted_value),
            "response_error": piece.response_error})
    return sorted(result, key=lambda row: row["sequence"])


def _score_row(score):
    raw = score.model_dump(mode="json")
    return {key: raw[key] for key in ("id", "message_piece_id", "status", "score_value", "score_type", "scorer_class_identifier", "objective")}


async def _run_campaign_async(plan, client):
    parts = _components(); memory = _memory(parts)
    inventory_before = client.inventory(); p.validate_model(inventory_before)
    controls = []
    scorer = _assembly(parts, p.INTERFACES[0], "positive")[2]
    for control in p.scorer_controls():
        message = parts["Message"].from_prompt(prompt=control["text"], role="assistant")
        message.get_piece().conversation_id = str(uuid.uuid4())
        memory.add_message_to_memory(request=message)
        scores = await scorer.score_async(scorable=parts["MessageScorable"].from_message(message),
            expectation=parts["ScoringExpectation"](objective="Fixed public lexical calibration"))
        if len(scores) != 1 or scores[0].get_value() is not control["expected_score"]: raise ValueError("Upstream lexical control failed")
        controls.append({**control, "upstream_score": scores[0].get_value(), "valid": True})
    runs = []
    for frozen in plan["identifiers"]:
        memory.reset_database()
        if memory.get_message_pieces() or memory.get_scores(score_type="true_false"): raise ValueError("Campaign memory did not reset")
        case_id, mode = frozen["case_id"], frozen["mode"]
        target, attacker, scorer, attack, identity = _assembly(parts, case_id, mode, client)
        p.same(identity, frozen)
        result = await attack.execute_async(objective=p.OBJECTIVES[case_id], memory_labels={"fixture_only": "true", "case_id": case_id, "mode": mode})
        if not target.records or not attacker.records: raise ValueError("Upstream attack did not execute the declared roles")
        cid, aid = result.conversation_id, attacker.records[0]["conversation_id"]
        pieces = memory.get_message_pieces()
        if set(piece.conversation_id for piece in pieces) != {cid, aid}: raise ValueError("Undeclared memory conversation")
        persisted_scores = memory.get_scores(score_type="true_false")
        score_map = {str(score.message_piece_id): score for score in persisted_scores}
        if (len(persisted_scores) != len(target.records) or len(score_map) != len(target.records)
                or len({str(score.id) for score in persisted_scores}) != len(persisted_scores)):
            raise ValueError("Unexpected upstream score roster")
        scores = [_score_row(score_map[call["response_id"]]) for call in target.records]
        saved = memory.get_attack_results(conversation_id=cid)
        if len(saved) != 1 or saved[0].attack_result_id != result.attack_result_id:
            raise ValueError("The upstream attack result was not persisted")
        normalized_result = {"conversation_id": cid, "adversarial_conversation_id": aid,
            "executed_turns": result.executed_turns, "outcome": result.outcome.value, "total_retries": result.total_retries,
            "last_score_id": str(result.last_score.id) if result.last_score else None,
            "last_response_id": str(result.last_response.id) if result.last_response else None,
            "reset_ids": list(target.reset_ids), "atomic_attack_identifier": result.atomic_attack_identifier.model_dump(mode="json")}
        runs.append({"case_id": case_id, "mode": mode, "identifiers": identity,
            "attacker_calls": p.owned(attacker.records), "target_calls": p.owned(target.records),
            "target_memory": _message_rows(memory, cid), "attacker_memory": _message_rows(memory, aid),
            "scores": scores, "result": normalized_result, "memory_reset_confirmed": True})
    try: inventory_after = client.inventory()
    except Exception as exc: inventory_after = {"error": type(exc).__name__, "fixture_inventory_failed": True}
    campaign = {"runs": runs, "inventory": {"before": inventory_before, "after": inventory_after}, "scorer_controls": controls,
        "path_binding": check_paths(), "target_calls": sum(len(row["target_calls"]) for row in runs if row["mode"] == "target")}
    p.replay_campaign(plan, campaign)
    return p.owned(campaign)


def run_campaign(plan, *, client=None):
    plan = p.validate_plan(plan)
    return asyncio.run(_run_campaign_async(plan, LoopbackClient() if client is None else client))
