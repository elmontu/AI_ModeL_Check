"""Real bounded adaptive PyRIT loop using shared local model roles."""
from __future__ import annotations
import asyncio
from ..production_pyrit import upstream as trusted
from ..production_adapters.contracts import canonical_bytes
from . import protocol as p
from .client import AdaptiveLoopbackClient, build_payload
_PARTS=None


def _parts():
    global _PARTS
    if _PARTS is not None:trusted.check_paths();return _PARTS
    parts=trusted._components()
    from pyrit.models import get_common_json_schema
    schema=p.validate_schema(get_common_json_schema("adversarial_chat"))
    PromptTarget=parts["FixedScriptedAttacker"].__bases__[0]
    Message=parts["Message"];MessagePiece=parts["MessagePiece"]
    class LocalAdaptiveAttacker(PromptTarget):
        _DEFAULT_CONFIGURATION=parts["FixedScriptedAttacker"]._DEFAULT_CONFIGURATION
        def __init__(self,*,case_id,client=None):
            self.case_id,self.client,self.records=case_id,client,[]
            super().__init__(model_name=p.MODEL_NAME,endpoint=trusted.BASE)
        def _build_identifier(self):
            return self._create_identifier(params={"role":"attacker","case_id":self.case_id,"model_digest":p.MODEL_DIGEST,
                "system_template_sha256":p.text_sha(p.ATTACKER_SYSTEM_TEMPLATE),"schema_sha256":p.SCHEMA_SHA256,"options":dict(p.ATTACKER_OPTIONS),
                "parser":"strict_exact_strings_no_repairs/v1","shared_model":True,"inert_tools":True})
        async def _send_prompt_to_target_async(self,*,normalized_conversation):
            history=trusted._history(normalized_conversation);turn=len(self.records)+1
            if turn>3:raise ValueError("Attacker turn bound exhausted")
            request=normalized_conversation[-1].get_piece()
            metadata=p.owned(request.prompt_metadata);p.validate_schema(metadata.get("json_schema"))
            messages=[{"role":row["role"],"content":row["text"]} for row in history]
            payload=build_payload("attacker",messages,format_schema=schema)
            try:raw=p.owned(self.client.chat("attacker",messages,format_schema=schema))
            except Exception as exc:raw={"error":type(exc).__name__,"fixture_request_failed":True}
            observation=p.normalize_attacker_response(raw)
            response=Message(message_pieces=[MessagePiece(role="assistant",original_value=observation["text"] or "",
                response_error="none" if observation["status"]=="accepted" else "processing")])
            self.records.append({"turn":turn,"conversation_id":request.conversation_id,"history":history,"actual_messages":messages,
                "request_metadata":metadata,"format_schema":schema,"wire_payload":payload,"request_id":str(request.id),"response_id":str(response.get_piece().id),"response":raw,"observation":observation})
            return [response]
    class AdaptiveObjectiveTarget(PromptTarget):
        _DEFAULT_CONFIGURATION=parts["FixedObjectiveTarget"]._DEFAULT_CONFIGURATION
        def __init__(self,*,case_id,client=None):
            self.case_id,self.client,self.records,self.reset_ids=case_id,client,[],[]
            super().__init__(model_name=p.MODEL_NAME,endpoint=trusted.BASE)
        def _build_identifier(self):
            return self._create_identifier(params={"role":"target","case_id":self.case_id,"model_digest":p.MODEL_DIGEST,
                "system_sha256":p.text_sha(p.TARGET_SYSTEM),"options":dict(p.TARGET_OPTIONS),"wrapper":"fixed_synthetic_document/v1","shared_model":True,"inert_tools":True})
        async def reset_conversation_async(self,*,conversation_id):self.reset_ids.append(conversation_id)
        async def _send_prompt_to_target_async(self,*,normalized_conversation):
            history=trusted._history(normalized_conversation);turn=len(self.records)+1
            if turn>3:raise ValueError("Target turn bound exhausted")
            messages=p.target_messages(self.case_id,history);payload=build_payload("target",messages)
            try:raw=p.owned(self.client.chat("target",messages))
            except Exception as exc:raw={"error":type(exc).__name__,"fixture_request_failed":True}
            observation=p.observe_target_response(raw)
            response=Message(message_pieces=[MessagePiece(role="assistant",original_value=observation["text"] or "",
                response_error="none" if observation["status"]=="scored" else "processing")])
            request=normalized_conversation[-1].get_piece()
            self.records.append({"turn":turn,"conversation_id":request.conversation_id,"history":history,"actual_messages":messages,"wire_payload":payload,
                "request_id":str(request.id),"response_id":str(response.get_piece().id),"response":raw,"observation":observation})
            return [response]
    for cls in (LocalAdaptiveAttacker,AdaptiveObjectiveTarget):cls.__module__=__name__;cls.__qualname__=cls.__name__
    _PARTS={**parts,"LocalAdaptiveAttacker":LocalAdaptiveAttacker,"AdaptiveObjectiveTarget":AdaptiveObjectiveTarget,"response_schema":schema}
    trusted.check_paths();return _PARTS


def _assembly(parts,case_id,mode,client=None):
    if mode!="adaptive":return trusted._assembly(parts,case_id,mode)
    target=parts["AdaptiveObjectiveTarget"](case_id=case_id,client=client)
    attacker=parts["LocalAdaptiveAttacker"](case_id=case_id,client=client)
    scorer=parts["SubStringScorer"](substring=p.MARKER,text_matcher=parts["ExactTextMatching"](case_sensitive=True,ignore_whitespace=False))
    attack=parts["RedTeamingAttack"](objective_target=target,
        attack_adversarial_config=parts["AttackAdversarialConfig"](target=attacker,system_prompt=p.ATTACKER_SYSTEM_TEMPLATE,first_message=p.FIRST_TEMPLATE,adversarial_prompt_template=p.NEXT_TEMPLATE),
        attack_scoring_config=parts["AttackScoringConfig"](objective_scorer=scorer,use_score_as_feedback=False),prompt_normalizer=parts["PromptNormalizer"](),max_turns=3,score_last_turn_only=False)
    atomic=parts["AtomicAttackIdentifier"].build(attack_identifier=attack.get_identifier())
    atomic=atomic.with_eval_hash(parts["AtomicAttackEvaluationIdentifier"](atomic).eval_hash)
    identity={"case_id":case_id,"mode":mode,"objective_target":target.get_identifier().model_dump(mode="json"),"adversarial_chat":attacker.get_identifier().model_dump(mode="json"),
        "objective_scorer":scorer.get_identifier().model_dump(mode="json"),"attack":attack.get_identifier().model_dump(mode="json"),"atomic_attack":atomic.model_dump(mode="json")}
    return target,attacker,scorer,attack,p.owned(identity)


def build_identifiers():
    parts=_parts();memory=trusted._memory(parts)
    identities=[_assembly(parts,case_id,mode)[4] for case_id in p.INTERFACES for mode in p.MODES]
    if memory.get_message_pieces() or memory.get_scores(score_type="true_false"):raise ValueError("Preparation performed inference")
    return p.validate_identifiers(identities)


def response_schema():return p.validate_schema(_parts()["response_schema"])


def check_paths():return trusted.check_paths()


def _memory_rows(memory,cid,mode):
    rows=trusted._message_rows(memory,cid)
    if mode!="adaptive":return rows
    pieces={str(piece.id):piece for piece in memory.get_message_pieces(conversation_id=cid)}
    return [{**row,"upstream_piece":pieces[row["id"]].model_dump(mode="json")} for row in rows]


def _summary(result,aid,target):
    return {"conversation_id":result.conversation_id,"adversarial_conversation_id":aid,"executed_turns":result.executed_turns,"outcome":result.outcome.value,"total_retries":result.total_retries,
        "last_score_id":str(result.last_score.id) if result.last_score else None,"last_response_id":str(result.last_response.id) if result.last_response else None,
        "reset_ids":list(target.reset_ids),"atomic_attack_identifier":result.atomic_attack_identifier.model_dump(mode="json") if result.atomic_attack_identifier else None,
        "upstream_result":result.model_dump(mode="json")}


async def _run_async(plan,client):
    parts=_parts();memory=trusted._memory(parts);before=client.inventory();p.validate_model(before)
    controls=[];scorer=_assembly(parts,p.INTERFACES[0],"positive")[2]
    import uuid
    for control in p.scorer_controls():
        message=parts["Message"].from_prompt(prompt=control["text"],role="assistant");message.get_piece().conversation_id=str(uuid.uuid4());memory.add_message_to_memory(request=message)
        scores=await scorer.score_async(scorable=parts["MessageScorable"].from_message(message),expectation=parts["ScoringExpectation"](objective="Fixed public lexical calibration"))
        if len(scores)!=1 or scores[0].get_value() is not control["expected_score"]:raise ValueError("Actual lexical calibration failed")
        controls.append({**control,"upstream_score":scores[0].get_value(),"valid":True})
    runs=[]
    for frozen in plan["identifiers"]:
        memory.reset_database()
        if memory.get_message_pieces() or memory.get_scores(score_type="true_false"):raise ValueError("Memory did not reset")
        case_id,mode=frozen["case_id"],frozen["mode"]
        target,attacker,scorer,attack,identity=_assembly(parts,case_id,mode,client);p.same(identity,frozen)
        terminal=None
        try:result=await attack.execute_async(objective=p.OBJECTIVES[case_id],memory_labels={"fixture_only":"true","case_id":case_id,"mode":mode})
        except Exception as exc:
            if mode!="adaptive" or not attacker.records or attacker.records[-1]["observation"]["status"]!="unusable":raise
            aid=attacker.records[0]["conversation_id"]
            results=memory.get_attack_results(outcome="error")
            if len(results)!=1:raise ValueError("Actual upstream error result was not persisted") from exc
            result=results[0]
            terminal={"phase":"attacker","exception_type":type(exc).__name__,"cause_type":type(exc.__cause__).__name__,"reason":attacker.records[-1]["observation"]["reason"]}
        if not attacker.records:raise ValueError("Actual attacker role was not invoked")
        cid,aid=result.conversation_id,attacker.records[0]["conversation_id"]
        pieces=memory.get_message_pieces()
        if set(piece.conversation_id for piece in pieces)-{cid,aid}:raise ValueError("Unexpected memory conversation")
        persisted=memory.get_scores(score_type="true_false");score_map={str(score.message_piece_id):score for score in persisted}
        if len(persisted)!=len(target.records) or len(score_map)!=len(target.records) or len({str(score.id) for score in persisted})!=len(persisted):raise ValueError("Unexpected actual score roster")
        scores=[trusted._score_row(score_map[call["response_id"]]) for call in target.records]
        if mode=="adaptive":
            scores=[{**score,"upstream_score":score_map[score["message_piece_id"]].model_dump(mode="json")} for score in scores]
        saved=memory.get_attack_results(conversation_id=cid)
        if len(saved)!=1 or saved[0].attack_result_id!=result.attack_result_id:raise ValueError("Actual upstream result is not persisted")
        summary=_summary(result,aid,target)
        if mode!="adaptive":summary.pop("upstream_result")
        runs.append({"case_id":case_id,"mode":mode,"identifiers":identity,"attacker_calls":p.owned(attacker.records),"target_calls":p.owned(target.records),
            "target_memory":_memory_rows(memory,cid,mode),"attacker_memory":_memory_rows(memory,aid,mode),"scores":scores,"result":summary,"memory_reset_confirmed":True,"terminal_error":terminal})
    try:after=client.inventory()
    except Exception as exc:after={"error":type(exc).__name__,"fixture_inventory_failed":True}
    campaign={"runs":runs,"inventory":{"before":before,"after":after},"scorer_controls":controls,"path_binding":check_paths(),"attacker_calls":client.counters["attacker"],"target_calls":client.counters["target"],
        "client":{"counters":client.counters,"inventory_calls":client.inventory_calls,"requests":client.requests}}
    p.replay_campaign(plan,campaign);return p.owned(campaign)


def run_campaign(plan,*,client=None):
    return asyncio.run(_run_async(p.validate_plan(plan),AdaptiveLoopbackClient() if client is None else client))
