"""Pure adaptive evidence fixtures; optional framework dependencies are never imported."""
from __future__ import annotations
import copy
import json
import unittest
import uuid
from model_release_assurance.production_pyrit_adaptive import protocol as p, runtime as r
from model_release_assurance.production_pyrit_adaptive.client import build_payload
import test_production_pyrit_protocol as prior

fixture_cache_binding=prior.fixture_cache_binding
fixture_response=prior.fixture_response


def fixture_plan(*,source_sha256="a"*64,lock_sha256="b"*64):
    identities=copy.deepcopy(prior.fixture_plan()["identifiers"])
    for row in identities:
        if row["mode"]=="target":
            row["mode"]="adaptive"
            for role,name in (("objective_target","AdaptiveObjectiveTarget"),("adversarial_chat","LocalAdaptiveAttacker")):
                row[role]["class_name"]=name
                row[role]["class_module"]="model_release_assurance.production_pyrit_adaptive.upstream"
                row[role]["hash"]=p.text_sha(row["case_id"]+"/adaptive/"+role)
    return p.make_plan(model=p.MODEL,runtime=r.expected_binding(),source_sha256=source_sha256,lock_sha256=lock_sha256,identifiers=identities)


def fixture_attacker_failure(text="{malformed",**changes):
    return fixture_response(text,**changes)


def fixture_campaign(plan,*,response=None,cache_root=None,attacker_response=None,fail_turn=1,failure_cases=None):
    old_plan=prior.fixture_plan(source_sha256=plan["source_sha256"],lock_sha256=plan["lock_sha256"])
    old_rows=prior.fixture_campaign(old_plan)["runs"]
    counter=1000
    def identifier():
        nonlocal counter
        counter+=1
        return str(uuid.UUID(int=counter,version=4))
    def piece(role,text,cid,sequence,error="none",metadata=None):
        mid=identifier();digest=None if role=="system" else p.text_sha(text)
        raw={"id":mid,"role":role,"conversation_id":cid,"sequence":sequence,"timestamp":"2026-10-06T00:00:00Z",
            "original_value":text,"converted_value":text,"original_value_data_type":"text","converted_value_data_type":"text",
            "original_value_sha256":digest,"converted_value_sha256":digest,"response_error":error,"original_prompt_id":mid,
            "prompt_metadata":copy.deepcopy(metadata or {}),"converter_identifiers":[]}
        return {"id":mid,"role":role,"text":text,"original_text":text,"conversation_id":cid,"sequence":sequence,
            "original_sha256":digest,"converted_sha256":digest,"recomputed_original_sha256":p.text_sha(text),
            "recomputed_converted_sha256":p.text_sha(text),"response_error":error,"upstream_piece":raw}
    runs=[];requests=[];counts={"attacker":0,"target":0}
    def request(role,payload,raw):
        counts[role]+=1
        receipt={"role":role,"role_call":counts[role],"payload":copy.deepcopy(payload),"status":"completed"}
        if raw.get("fixture_request_failed") is True:receipt.update(status="error",error_type=raw["error"])
        requests.append(receipt)
    for index,identity in enumerate(plan["identifiers"]):
        if identity["mode"]!="adaptive":
            row=copy.deepcopy(old_rows[index]);row["terminal_error"]=None;runs.append(row);continue
        case=identity["case_id"];cid,aid=identifier(),identifier();amemory=[];tmemory=[];attackers=[];targets=[];scores=[];ah=[];th=[];previous=None;terminal=None
        system=p.ATTACKER_SYSTEM_TEMPLATE.replace("{{ objective }}",p.OBJECTIVES[case]).replace("{{ max_turns }}","3")
        ah.append({"role":"system","text":system});amemory.append(piece("system",system,aid,0))
        for turn in range(1,4):
            user=p.FIRST_TEMPLATE.replace("{{ objective }}",p.OBJECTIVES[case]) if turn==1 else "TARGET_FEEDBACK: "+(previous["text"] if previous["status"]=="scored" else "Request to target failed: processing")
            ah.append({"role":"user","text":user})
            messages=[{"role":x["role"],"content":x["text"]} for x in ah]
            metadata={"response_format":"json","json_schema":copy.deepcopy(p.RESPONSE_SCHEMA),"json_schema_name":"CustomSchema","json_schema_strict":True}
            reply={"next_message":"Public synthetic prompt turn "+str(turn),"rationale":"Use the public context.","last_response_summary":"" if previous is None else "Observed the previous public reply."}
            raw=fixture_response(json.dumps(reply,separators=(",",":")))
            if attacker_response is not None and turn==fail_turn and (failure_cases is None or case in failure_cases):raw=copy.deepcopy(attacker_response)
            obs=p.normalize_attacker_response(raw);ar=piece("user",user,aid,len(amemory),metadata=metadata)
            aa=piece("assistant",obs["text"] or "",aid,len(amemory)+1,"none" if obs["status"]=="accepted" else "processing")
            payload=build_payload("attacker",messages,format_schema=p.RESPONSE_SCHEMA)
            attackers.append({"turn":turn,"conversation_id":aid,"history":copy.deepcopy(ah),"actual_messages":messages,"request_metadata":metadata,
                "format_schema":copy.deepcopy(p.RESPONSE_SCHEMA),"wire_payload":payload,"request_id":ar["id"],"response_id":aa["id"],"response":raw,"observation":obs})
            request("attacker",payload,raw);amemory.extend([ar,aa]);ah.append({"role":"assistant","text":obs["text"] or ""})
            if obs["status"]!="accepted":
                terminal={"phase":"attacker","exception_type":"_StrategyRuntimeError","cause_type":"PyritException","reason":obs["reason"]};break
            next_message=obs["reply"]["next_message"];th.append({"role":"user","text":next_message})
            history=p.old.replayable_target_history(th);messages=p.target_messages(case,th);payload=build_payload("target",messages)
            raw=fixture_response() if response is None else copy.deepcopy(response)
            previous=p.observe_target_response(raw);tr=piece("user",next_message,cid,len(tmemory))
            ta=piece("assistant",previous["text"] or "",cid,len(tmemory)+1,"none" if previous["status"]=="scored" else "processing")
            targets.append({"turn":turn,"conversation_id":cid,"history":copy.deepcopy(history),"actual_messages":messages,"wire_payload":payload,
                "request_id":tr["id"],"response_id":ta["id"],"response":raw,"observation":copy.deepcopy(previous)})
            request("target",payload,raw);tmemory.extend([tr,ta]);th.append({"role":"assistant","text":previous["text"] or "","response_error":ta["response_error"]})
            score={"id":identifier(),"message_piece_id":ta["id"],"status":"complete" if previous["status"]=="scored" else "undetermined",
                "score_value":str(previous["score"]).lower() if previous["status"]=="scored" else None,"score_type":"true_false",
                "scorer_class_identifier":copy.deepcopy(identity["objective_scorer"]),"objective":p.OBJECTIVES[case]}
            score["upstream_score"]={**copy.deepcopy(score),"score_value_description":None,"score_category":[],"score_rationale":"Public literal fixture.",
                "score_metadata":{},"scorable":{"scorable_type":"message","message_piece_ids":[ta["id"]]},"timestamp":"2026-10-06T00:00:00Z"}
            scores.append(score)
            if previous["score"] is True:break
        raw_result={"conversation_id":cid,"objective":p.OBJECTIVES[case],"executed_turns":0 if terminal else len(targets),
            "outcome":"error" if terminal else "success" if previous["score"] is True else "failure" if previous["score"] is False else "undetermined",
            "total_retries":0,"retry_events":[],"last_score":None if terminal else copy.deepcopy(scores[-1]["upstream_score"]),
            "last_response":None if terminal else copy.deepcopy(tmemory[-1]["upstream_piece"]),"atomic_attack_identifier":None if terminal else copy.deepcopy(identity["atomic_attack"]),
            "related_conversations":[{"conversation_id":aid,"conversation_type":"adversarial","description":"adversarial chat conversation" if terminal else None}],
            "labels":{"case_id":case,"fixture_only":"true","mode":"adaptive"},"metadata":{},"attribution_parent_id":None,"attribution_data":None,"targeted_harm_categories":[],
            "error_type":"PyritException" if terminal else None,"error_message":"Status Code: 500, Message: Adversarial chat returned a processing error: "+(attackers[-1]["observation"]["text"] or "") if terminal else None,
            "error_traceback":"Synthetic fixture records the upstream error boundary." if terminal else None}
        result={"conversation_id":cid,"adversarial_conversation_id":aid,"executed_turns":raw_result["executed_turns"],"outcome":raw_result["outcome"],"total_retries":0,
            "last_score_id":None if terminal else scores[-1]["id"],"last_response_id":None if terminal else targets[-1]["response_id"],"reset_ids":[cid] if targets else [],
            "atomic_attack_identifier":copy.deepcopy(raw_result["atomic_attack_identifier"]),"upstream_result":raw_result}
        runs.append({"case_id":case,"mode":"adaptive","identifiers":copy.deepcopy(identity),"attacker_calls":attackers,"target_calls":targets,"target_memory":tmemory,
            "attacker_memory":amemory,"scores":scores,"result":result,"memory_reset_confirmed":True,"terminal_error":terminal})
    return {"runs":runs,"inventory":{"before":dict(p.MODEL),"after":dict(p.MODEL)},"scorer_controls":[{**c,"upstream_score":c["expected_score"],"valid":True} for c in p.scorer_controls()],
        "path_binding":fixture_cache_binding(cache_root),"target_calls":counts["target"],"attacker_calls":counts["attacker"],"client":{"counters":counts,"inventory_calls":2,"requests":requests}}


def fixture_output(plan,**kwargs):
    campaign=fixture_campaign(plan,**kwargs);summary=p.replay_campaign(plan,campaign)
    return {"schema":"mra-pyrit-adaptive-worker-output/v1","mode":"run","status":summary["status"],"runtime":copy.deepcopy(plan["runtime"]),"versions":dict(r.LOCKED_VERSIONS),
        "source_sha256":plan["source_sha256"],"lock_sha256":plan["lock_sha256"],"model":dict(p.MODEL),"plan_sha256":p.sha(plan),"campaign":campaign,"replay":summary,
        "path_binding":copy.deepcopy(campaign["path_binding"]),**p.ROLE_FLAGS,**p.FLAGS}


class AdaptiveProtocolTests(unittest.TestCase):
    def test_bounded_shared_model_campaign_replays_histories(self):
        plan=fixture_plan();output=fixture_output(plan);summary=p.replay(plan,output)
        self.assertEqual(summary["status"],"completed")
        self.assertEqual((summary["attacker_calls"],summary["target_turns"]),(6,6))
        self.assertEqual([len(row["target_calls"]) for row in output["campaign"]["runs"]],[2,3,3,2,3,3])
        self.assertIs(summary["shared_model"],True)
        for key in ("independent_models","independent_attacker_model","production_authorized","can_clear","network_isolated","hostile_code_isolated"):self.assertIs(summary[key],False)
        row=output["campaign"]["runs"][2]
        self.assertNotEqual(row["result"]["conversation_id"],row["result"]["adversarial_conversation_id"])
        self.assertEqual(row["attacker_calls"][1]["history"][-1]["text"],"TARGET_FEEDBACK: A public grammar exercise.")

    def test_terminal_malformed_has_zero_target_calls_and_actual_zero_turn_result(self):
        plan=fixture_plan();output=fixture_output(plan,attacker_response=fixture_attacker_failure())
        summary=p.replay(plan,output)
        self.assertEqual((summary["status"],summary["attacker_calls"],summary["target_turns"],summary["attacker_failures"]),("incomplete",2,0,2))
        for row in (output["campaign"]["runs"][2],output["campaign"]["runs"][5]):
            self.assertEqual(row["target_calls"],[]);self.assertEqual(row["target_memory"],[])
            self.assertEqual(row["attacker_memory"][-1]["text"],"{malformed")
            self.assertEqual(row["attacker_memory"][-1]["response_error"],"processing")
            self.assertEqual(row["result"]["upstream_result"]["executed_turns"],0)
            self.assertIsNone(row["result"]["upstream_result"]["last_response"])

    def test_actual_terminal_conversation_description_is_preserved(self):
        # PyRIT 1.1.0 actual retained malformed fixture records this error-specific description.
        plan=fixture_plan();output=fixture_output(plan,attacker_response=fixture_attacker_failure())
        raw=output["campaign"]["runs"][2]["result"]["upstream_result"]
        self.assertEqual(raw["related_conversations"][0]["description"],"adversarial chat conversation")
        raw["related_conversations"][0]["description"]=None
        with self.assertRaises(ValueError):p.replay(plan,output)

    def test_partial_target_then_transport_error_preserves_prior_score(self):
        plan=fixture_plan();output=fixture_output(plan,attacker_response={"error":"OSError","fixture_request_failed":True},fail_turn=2)
        summary=p.replay(plan,output)
        self.assertEqual((summary["attacker_calls"],summary["target_turns"],summary["scored"]),(4,2,2))
        row=output["campaign"]["runs"][2]
        self.assertEqual(row["result"]["executed_turns"],0)
        self.assertEqual(len(row["scores"]),1)
        self.assertEqual(row["scores"][0]["score_value"],"false")
        self.assertEqual(output["campaign"]["client"]["requests"][2]["status"],"error")
        self.assertIsNone(row["attacker_calls"][-1]["observation"]["reply"])

    def test_unscoreable_target_hit_remains_incomplete_and_filters_failed_pairs(self):
        plan=fixture_plan();output=fixture_output(plan,response=fixture_response(p.MARKER,done=False))
        summary=p.replay(plan,output);row=output["campaign"]["runs"][2]
        self.assertEqual((summary["status"],summary["unscoreable"],summary["observed_literal_hits"]),("incomplete",6,6))
        self.assertEqual([len(call["history"]) for call in row["target_calls"]],[1,1,1])
        self.assertEqual(row["target_memory"][1]["text"],p.MARKER)
        self.assertEqual(row["attacker_calls"][1]["history"][-1]["text"],"TARGET_FEEDBACK: Request to target failed: processing")

    def test_attacker_truncated_marker_is_separate_from_target_hits(self):
        plan=fixture_plan();output=fixture_output(plan,attacker_response=fixture_attacker_failure(p.MARKER,done=False))
        summary=p.replay(plan,output)
        self.assertEqual((summary["attacker_literal_marker_observations"],summary["observed_literal_hits"],summary["target_turns"]),(2,0,0))
        self.assertEqual(output["campaign"]["runs"][2]["attacker_calls"][0]["response"]["message"]["content"],p.MARKER)

    def test_strict_attacker_json_rejects_coercion_aliases_duplicates_and_repairs(self):
        base={"next_message":"Public prompt","rationale":"","last_response_summary":""}
        texts=["not JSON","```json\n"+json.dumps(base)+"\n```",json.dumps({**base,"next_message":3}),json.dumps({**base,"next_message":False}),
            json.dumps({**base,"next_message":" "}),json.dumps({**base,"rationale":"x"*257}),json.dumps({**base,"last_response_summary":"x"*257}),
            json.dumps({**base,"next_message":"x"*1025}),json.dumps({**base,"extra":"x"}),json.dumps({"nextMessage":"x","rationale":"","lastResponseSummary":""}),
            '{"next_message":"x","next_message":"y","rationale":"","last_response_summary":""}']
        for text in texts:
            with self.subTest(text=text[:100]):
                obs=p.normalize_attacker_response(fixture_response(text))
                self.assertEqual(obs["status"],"unusable");self.assertEqual(obs["reason"],"invalid_attacker_json");self.assertIsNone(obs["reply"])
        self.assertEqual(p.normalize_attacker_response(fixture_response(json.dumps(base),eval_count=512))["status"],"accepted")

    def test_attacker_provider_failures_keep_raw_public_marker(self):
        good=json.dumps({"next_message":p.MARKER,"rationale":"","last_response_summary":""})
        for changes in ({"done":False},{"done_reason":"length"},{"model":"other"},{"eval_count":True},{"eval_count":513},{"prompt_eval_count":4097},
            {"message":{"role":"assistant","content":good,"tool_calls":[{"function":{"name":"inert"}}]}}):
            with self.subTest(changes=changes):
                obs=p.normalize_attacker_response(fixture_response(good,**changes))
                self.assertEqual(obs["status"],"unusable");self.assertTrue(obs["observed_literal_hit"]);self.assertIsNone(obs["reply"])

    def test_same_id_changed_embedded_final_score_and_response_are_rejected(self):
        mutations=[
            lambda raw:raw["last_score"].update(score_value="true"),lambda raw:raw["last_score"].update(objective="changed"),
            lambda raw:raw["last_score"]["scorer_class_identifier"].update(hash="c"*64),lambda raw:raw["last_score"].update(score_rationale="changed"),
            lambda raw:raw["last_response"].update(role="user"),lambda raw:raw["last_response"].update(original_value="changed"),
            lambda raw:raw["last_response"].update(converted_value="changed"),lambda raw:raw["last_response"].update(response_error="processing"),
            lambda raw:raw["last_response"].update(original_value_sha256="c"*64),lambda raw:raw["last_response"].update(prompt_metadata={"changed":True})]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                plan=fixture_plan();output=fixture_output(plan);raw=output["campaign"]["runs"][2]["result"]["upstream_result"]
                score_id,response_id=raw["last_score"]["id"],raw["last_response"]["id"];mutate(raw)
                self.assertEqual((raw["last_score"]["id"],raw["last_response"]["id"]),(score_id,response_id))
                with self.assertRaises(ValueError):p.replay(plan,output)

    def test_full_persisted_role_metadata_must_match_wire_schema(self):
        for index in (0,1,2):
            with self.subTest(index=index):
                plan=fixture_plan();output=fixture_output(plan);row=output["campaign"]["runs"][2]
                row["attacker_memory"][index]["upstream_piece"]["prompt_metadata"]={"json_schema":{"type":"string"}}
                with self.assertRaises(ValueError):p.replay(plan,output)
        plan=fixture_plan();output=fixture_output(plan);row=output["campaign"]["runs"][2]
        row["target_memory"][-1]["upstream_piece"]["prompt_metadata"]={"changed":True}
        row["result"]["upstream_result"]["last_response"]["prompt_metadata"]={"changed":True}
        with self.assertRaises(ValueError):p.replay(plan,output)

    def test_coupling_schema_identity_counters_and_lifecycle_tampering_rejected(self):
        mutations=[
            lambda x:x["campaign"]["runs"][2]["attacker_calls"][1]["history"][-1].update(text="cached feedback"),
            lambda x:x["campaign"]["runs"][2]["attacker_calls"][0]["request_metadata"].update(json_schema={"type":"string"}),
            lambda x:x["campaign"]["runs"][2]["attacker_calls"][0]["wire_payload"].update(format={"type":"string"}),
            lambda x:x["campaign"]["runs"][2]["target_calls"][1]["history"][0].update(text="other role history"),
            lambda x:x["campaign"]["client"]["counters"].update(attacker=7),
            lambda x:x["campaign"]["client"]["requests"][0].update(role="target"),
            lambda x:x["campaign"]["runs"][2]["result"]["upstream_result"]["related_conversations"][0].update(conversation_id=x["campaign"]["runs"][2]["result"]["conversation_id"]),
            lambda x:x["campaign"]["runs"][2]["result"]["upstream_result"].update(labels={}),
            lambda x:x["campaign"]["runs"][2]["scores"][0].update(id=x["campaign"]["runs"][2]["attacker_memory"][0]["id"]),
            lambda x:x.update(shared_model=False),lambda x:x.update(independent_attacker_model=True),
            lambda x:x["campaign"]["scorer_controls"][1].update(upstream_score=True)]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                plan=fixture_plan();output=fixture_output(plan);mutate(output)
                with self.assertRaises(ValueError):p.replay(plan,output)

    def test_model_inventory_drift_never_completes(self):
        plan=fixture_plan();campaign=fixture_campaign(plan);campaign["inventory"]["after"]={"error":"OSError"}
        self.assertEqual(p.replay_campaign(plan,campaign)["status"],"incomplete")
        self.assertFalse(p.replay_campaign(plan,campaign)["model_digest_stable"])


if __name__=="__main__":unittest.main()
