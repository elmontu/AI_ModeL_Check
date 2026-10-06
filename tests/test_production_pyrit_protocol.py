"""Independent receipt replay fixtures require no optional PyRIT runtime."""
from __future__ import annotations
import copy
from pathlib import PureWindowsPath
import uuid
import unittest
from model_release_assurance.production_pyrit import protocol as p, runtime as r
from model_release_assurance.production_adapters.contracts import canonical_bytes


def fixture_cache_binding(root=None):
    root = PureWindowsPath(str(root or "D:/ChatGPT/model_audit/AI_ModeL_Check_Government/.local/verification/unit-pyrit-cache"))
    return {"schema": "mra-pyrit-cache-binding/v1", "root": str(root), "db_data_path": str(root / "pyrit/dbdata"),
        "cache_path": str(root / "pyrit/.pyrit_cache"), "log_path": str(root / "pyrit/dbdata/logs.txt"),
        "hook": "trusted_fixed_appdirs_pyrit/v1", "profile_discovery": False}


def fixture_plan(*, source_sha256="a"*64, lock_sha256="b"*64):
    identities = []
    for case_id in p.INTERFACES:
        for mode in p.MODES:
            identity = {"case_id": case_id, "mode": mode}
            for role, name in (("objective_target", "FixedObjectiveTarget"), ("adversarial_chat", "FixedScriptedAttacker"),
                    ("objective_scorer", "SubStringScorer"), ("attack", "RedTeamingAttack")):
                identity[role] = {"class_name": name, "class_module": "model_release_assurance.production_pyrit.upstream" if role in ("objective_target", "adversarial_chat") else "pyrit.fixed_fixture",
                    "params": {"fixture": case_id + "/" + mode + "/" + role}, "children": {}, "pyrit_version": "1.1.0", "hash": p.text_sha(case_id + "/" + mode + "/" + role)}
            identity["atomic_attack"] = {"class_name": "AtomicAttack", "class_module": "pyrit.scenario.core.atomic_attack", "params": {},
                "children": {"attack_technique": {"children": {"attack": copy.deepcopy(identity["attack"])}}},
                "pyrit_version": "1.1.0", "hash": p.text_sha(case_id + "/" + mode + "/atomic")}
            identities.append(identity)
    return p.make_plan(model=p.MODEL,runtime=r.expected_binding(),source_sha256=source_sha256,lock_sha256=lock_sha256,identifiers=identities)


def fixture_response(text="A public grammar exercise.", **changes):
    return {"model": p.MODEL_NAME, "message": {"role": "assistant", "content": text},
        "done": True, "done_reason": "stop", "eval_count": 1, "prompt_eval_count": 1, **changes}


def fixture_campaign(plan, *, response=None, cache_root=None):
    count = 0
    def identifier():
        nonlocal count
        count += 1; return str(uuid.UUID(int=count, version=4))
    def piece(role, text, cid, sequence, error="none"):
        return {"id": identifier(), "role": role, "text": text, "original_text": text, "conversation_id": cid,
            "sequence": sequence, "original_sha256": None if role == "system" else p.text_sha(text), "converted_sha256": None if role == "system" else p.text_sha(text),
            "recomputed_original_sha256": p.text_sha(text), "recomputed_converted_sha256": p.text_sha(text), "response_error": error}
    runs = []
    for identity in plan["identifiers"]:
        case_id, mode = identity["case_id"], identity["mode"]
        cid, aid = identifier(), identifier(); target_memory, attacker_memory, targets, attackers, scores = [], [], [], [], []
        system = p.ATTACKER_SYSTEM_TEMPLATE.replace("{{ objective }}", p.OBJECTIVES[case_id])
        attacker_memory.append(piece("system", system, aid, 0)); target_history = []; attacker_history = [{"role": "system", "text": system}]
        previous = None
        for turn in range(1, 4):
            user = p.FIRST_TEMPLATE.replace("{{ objective }}", p.OBJECTIVES[case_id]) if turn == 1 else "TARGET_FEEDBACK: " + (previous["text"] if previous["status"] == "scored" else "Request to target failed: processing")
            reply = p.attacker_reply(case_id, turn); reply_text = canonical_bytes(reply).decode("utf-8")
            attacker_history.append({"role": "user", "text": user})
            ar = piece("user", user, aid, len(attacker_memory)); aa = piece("assistant", reply_text, aid, len(attacker_memory)+1)
            attackers.append({"turn": turn, "conversation_id": aid, "history": copy.deepcopy(attacker_history), "request_id": ar["id"], "response_id": aa["id"], "reply": reply})
            attacker_memory.extend([ar, aa]); attacker_history.append({"role": "assistant", "text": reply_text})
            text = p.control_text(mode, turn) if mode != "target" else "A public grammar exercise."
            raw = fixture_response(text) if mode != "target" or response is None else copy.deepcopy(response)
            previous = p.observe_response(raw)
            target_history.append({"role": "user", "text": reply["next_message"]})
            tr = piece("user", reply["next_message"], cid, len(target_memory))
            ta = piece("assistant", previous["text"] or "", cid, len(target_memory)+1, "none" if previous["status"] == "scored" else "processing")
            sent_history = p.replayable_target_history(target_history)
            messages = [{"role": "system", "content": p.TARGET_SYSTEM}] + [{"role": item["role"], "content": item["text"]} for item in sent_history]
            targets.append({"turn": turn, "conversation_id": cid, "history": copy.deepcopy(sent_history), "actual_messages": messages,
                "request_id": tr["id"], "response_id": ta["id"], "response": raw, "observation": copy.deepcopy(previous)})
            target_memory.extend([tr, ta]); target_history.append({"role": "assistant", "text": previous["text"] or "", "response_error": "none" if previous["status"] == "scored" else "processing"})
            scores.append({"id": identifier(), "message_piece_id": ta["id"], "status": "complete" if previous["status"] == "scored" else "undetermined",
                "score_value": str(previous["score"]).lower() if previous["status"] == "scored" else None, "score_type": "true_false",
                "scorer_class_identifier": copy.deepcopy(identity["objective_scorer"]), "objective": p.OBJECTIVES[case_id]})
            if previous["score"] is True: break
        result = {"conversation_id": cid, "adversarial_conversation_id": aid, "executed_turns": len(targets),
            "outcome": "success" if previous["score"] is True else "failure" if previous["score"] is False else "undetermined", "total_retries": 0,
            "last_score_id": scores[-1]["id"], "last_response_id": targets[-1]["response_id"], "reset_ids": [cid], "atomic_attack_identifier": copy.deepcopy(identity["atomic_attack"])}
        runs.append({"case_id": case_id, "mode": mode, "identifiers": copy.deepcopy(identity), "attacker_calls": attackers, "target_calls": targets,
            "target_memory": target_memory, "attacker_memory": attacker_memory, "scores": scores, "result": result, "memory_reset_confirmed": True})
    return {"runs": runs, "inventory": {"before": dict(p.MODEL), "after": dict(p.MODEL)}, "scorer_controls": [{**control, "upstream_score": control["expected_score"], "valid": True} for control in p.scorer_controls()],
        "path_binding": fixture_cache_binding(cache_root), "target_calls": sum(len(row["target_calls"]) for row in runs if row["mode"] == "target")}


def fixture_output(plan, *, response=None, cache_root=None):
    campaign = fixture_campaign(plan, response=response, cache_root=cache_root); summary = p.replay_campaign(plan, campaign)
    return {"schema": "mra-pyrit-worker-output/v1", "mode": "run", "status": summary["status"], "runtime": plan["runtime"], "versions": dict(r.LOCKED_VERSIONS),
        "source_sha256": plan["source_sha256"], "lock_sha256": plan["lock_sha256"], "model": dict(p.MODEL), "plan_sha256": p.sha(plan),
        "campaign": campaign, "replay": summary, "path_binding": copy.deepcopy(campaign["path_binding"]), **p.FLAGS}


class PyritProtocolTests(unittest.TestCase):
    def test_complete_replays_real_history_shape(self):
        plan=fixture_plan(); output=fixture_output(plan)
        self.assertEqual(p.replay(plan, output)["status"], "completed")
        self.assertEqual([len(row["target_calls"]) for row in output["campaign"]["runs"]], [2,3,3,2,3,3])
        self.assertEqual(output["replay"]["target_turns"], 6)
        self.assertIs(output["replay"]["production_authorized"], False)

    def test_unscoreable_hit_retained_and_cannot_clear(self):
        plan=fixture_plan(); output=fixture_output(plan,response=fixture_response(p.MARKER,done=False))
        self.assertEqual(output["replay"]["status"], "incomplete")
        self.assertEqual(output["replay"]["unscoreable"], 6)
        self.assertEqual(output["replay"]["observed_literal_hits"], 6)
        self.assertIsNone(output["campaign"]["runs"][2]["scores"][0]["score_value"])
        self.assertEqual(p.replay(plan,output)["human_review"], "pending")

    def test_failed_pairs_are_preserved_in_memory_and_omitted_from_wire_history(self):
        plan=fixture_plan(); output=fixture_output(plan,response=fixture_response(p.MARKER,done=False))
        row=output["campaign"]["runs"][2]
        self.assertEqual(len(row["target_memory"]),6)
        self.assertEqual([len(call["history"]) for call in row["target_calls"]],[1,1,1])
        self.assertEqual(row["target_memory"][1]["text"],p.MARKER)
        self.assertEqual(row["target_memory"][1]["response_error"],"processing")
        row["target_calls"][1]["history"].insert(0,{"role":"assistant","text":p.MARKER})
        with self.assertRaises(ValueError):p.replay(plan,output)

    def test_mutated_evidence_fails_closed(self):
        mutations=[
            lambda x: x["campaign"]["runs"][0]["scores"][0].update(id=x["campaign"]["runs"][1]["scores"][0]["id"]),
            lambda x: x["campaign"]["runs"][0]["scores"][0].update(id=x["campaign"]["runs"][0]["target_memory"][0]["id"]),
            lambda x: x["campaign"]["runs"][0]["result"]["atomic_attack_identifier"].update(params={"unrelated": True}),
            lambda x: x["campaign"]["runs"][0]["target_memory"][0].update(original_sha256="c"*64),
            lambda x: x["campaign"]["runs"][1]["attacker_calls"][1]["history"][2].update(text="tampered feedback"),
            lambda x: x["campaign"]["runs"][0]["scores"][0].update(message_piece_id=x["campaign"]["runs"][0]["target_calls"][1]["response_id"]),
            lambda x: x["campaign"]["runs"][0]["result"].update(executed_turns=True),
            lambda x: x["campaign"]["runs"][0]["result"].update(reset_ids=[]),
            lambda x: x["campaign"]["scorer_controls"][1].update(upstream_score=True),
            lambda x: x.update(production_authorized=True),
            lambda x: x["campaign"]["runs"][1]["target_calls"][0]["actual_messages"][0].update(content="changed system"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                plan=fixture_plan(); output=fixture_output(plan); mutate(output)
                with self.assertRaises(ValueError): p.replay(plan,output)

    def test_provider_boundaries_preserve_marker(self):
        for changes in [{"done":False}, {"done_reason":"length"}, {"model":"different"}, {"eval_count":True}, {"prompt_eval_count":4097}, {"error":"provider"}]:
            with self.subTest(changes=changes):
                observation=p.observe_response(fixture_response(p.MARKER,**changes))
                self.assertEqual(observation["status"], "unscoreable"); self.assertIsNone(observation["score"])
                self.assertIs(observation["observed_literal_hit"], True)

    def test_case_and_semantic_limitations_are_explicit(self):
        self.assertTrue(p.literal_hit(p.MARKER)); self.assertTrue(p.literal_hit("Do not print " + p.MARKER))
        self.assertFalse(p.literal_hit(p.MARKER.lower()))
        controls=p.scorer_controls(); self.assertEqual(len(controls),7); self.assertIs(controls[-1]["expected_score"],False)

    def test_cache_cannot_escape_government(self):
        for root in ["C:/Users/user/cache", "D:/ChatGPT/model_audit/AI_Model_Academic/.local/cache", "D:/ChatGPT/model_audit/AI_ModeL_Check_Government/.local/../outside"]:
            with self.subTest(root=root), self.assertRaises(ValueError): p.validate_cache_binding(fixture_cache_binding(root))


if __name__ == "__main__": unittest.main()
