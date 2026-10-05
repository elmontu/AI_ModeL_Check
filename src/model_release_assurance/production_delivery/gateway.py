"""One currently guarded public-fixture route from reviewed bytes to a writer.

Production is refused. Durable admissions precede byte release; observations
never infer recipient receipt. Trusted Python/bootstrap/filesystem are outside
this boundary. No caller artifact path, import, cached approval or direct read
method is exposed by this service.
"""
from __future__ import annotations

import hashlib
import uuid

from .authorization import GatewayAuthorization
from .contracts import FLAGS,DeliveryError,integer,validate_pin,canonical_bytes
from .store import DeliveryStore,StoreConflict,StoreUnavailable
from .review_bridge import DeliveryReviewBridge
from ..production_identity.policy import PermissionDenied


def _deny():
    raise PermissionDenied("Current scoped public-fixture delivery unavailable")


class FixtureDeliveryGateway:
    def __init__(self,bridge,store,recipients,*,expected_pin,checkpoint_sink):
        if type(bridge) is not DeliveryReviewBridge or type(store) is not DeliveryStore or not callable(checkpoint_sink):
            raise DeliveryError("Delivery fixture bootstrap rejected")
        self.bridge,self.review,self.store=bridge,bridge.review,store
        self.authorization=GatewayAuthorization(self.review,recipients)
        self._sink=checkpoint_sink;self._pin=validate_pin(expected_pin)
        self._proofs={};self._capability=store._bind_gateway(self)
        with self.review.identity._lock:
            current=store.inspect(expected_pin=self._pin,guard=self.review.identity._time)
            self._accept(current["pin"],self.review.identity._time)

    @property
    def required_pin(self):
        return dict(self._pin)

    def _accept(self,pin,guard):
        pin=validate_pin(pin)
        if (pin["store_id"]!=self._pin["store_id"] or pin["sequence"]<self._pin["sequence"]
                or pin["sequence"]==self._pin["sequence"] and pin!=self._pin):
            raise StoreConflict("Delivery history is below current floor")
        # Never discard a known newer floor even when persistence/response fails.
        self._pin=dict(pin)
        self._sink(dict(pin))
        return guard()

    def _state(self,context,case_id):
        state=self.store.get(case_id,expected_pin=self._pin,guard=context.recheck)
        if any(state["case"][k]!=getattr(context.case,k) for k in ("agency_id","project_id","case_id","submitter_person_id")):
            _deny()
        self._accept(state["pin"],context.recheck)
        return state

    @staticmethod
    def _record(state,group,key):
        if type(key) is not str or key not in state[group]:
            raise StoreConflict("Delivery reference unavailable")
        return state[group][key]

    def _proof(self,record):
        contexts=self._proofs.get(record["sha256"])
        if contexts is None:
            _deny()
        return contexts

    def _guard(self,context,frame,*,extra=(),deadlines=()):
        def current():
            self.bridge.recheck_frame(context.review_context,frame)
            now=self.authorization.recheck_many((context,*extra),review_contexts=frame["review_contexts"])
            if any(not begin<=now<end for begin,end in (*frame["deadlines"],*deadlines)):
                _deny()
            return now
        return current

    def _activation_frame(self,context,activation):
        payload=activation["payload"]
        frame=self.bridge.prepare(context.review_context,payload["campaign_id"])
        campaign=frame["campaign"]
        actual={"artifact_sha256":hashlib.sha256(frame["artifact"]).hexdigest(),
            "artifact_size":len(frame["artifact"]),"policy_sha256":campaign["policy_sha256"],
            "binding_sha256":campaign["binding_sha256"],"approval_sha256":campaign["approval"]["sha256"],
            "review_store_id":frame["review_snapshot"]["store_id"],
            "review_head_sha256":frame["review_snapshot"]["head_sha256"],
            "recipient_id":campaign["policy"]["recipient_id"]}
        if any(payload[k]!=v for k,v in actual.items()):
            _deny()
        return frame

    def activate(self,token,case_id,campaign_id,*,ttl_seconds=30,profile="agency_private_cloud"):
        if type(profile) is not str or profile!="local_public_fixture":
            raise DeliveryError("Production delivery is not qualified")
        integer(ttl_seconds,1,60)
        with self.review.identity._lock:
            context=self.authorization.access(token,case_id,"activate")
            state=self._state(context,case_id)
            frame=self.bridge.prepare(context.review_context,campaign_id)
            campaign=frame["campaign"];recipient=campaign["policy"]["recipient_id"]
            context=self.authorization.access(token,case_id,"activate",recipient)
            guard=self._guard(context,frame);now=guard()
            expiry=min(now+ttl_seconds,context.identity.expires_at,*(end for _,end in frame["deadlines"]),
                *(proof.identity.expires_at for proof in frame["review_contexts"]))
            if expiry<=now:
                _deny()
            payload={"schema":"mra-fixture-delivery-activation/v1","activation_id":uuid.uuid4().hex,
                "campaign_id":campaign_id,"agency_id":context.case.agency_id,
                "project_id":context.case.project_id,"case_id":case_id,"recipient_id":recipient,
                "artifact_sha256":hashlib.sha256(frame["artifact"]).hexdigest(),"artifact_size":len(frame["artifact"]),
                "policy_sha256":campaign["policy_sha256"],"binding_sha256":campaign["binding_sha256"],
                "approval_sha256":campaign["approval"]["sha256"],"review_store_id":frame["review_snapshot"]["store_id"],
                "review_head_sha256":frame["review_snapshot"]["head_sha256"],"expires_at":expiry,
                "format":"native_candidate_json","profile":profile}
            deadline_guard=self._guard(context,frame,deadlines=((now,expiry),))
            result=self.store._activate(case_id,payload,context.actor,artifact_bytes=frame["artifact"],
                capability=self._capability,expected_pin=self._pin,expected_head_sha256=state["head_sha256"],guard=deadline_guard)
            self._accept(result["pin"],deadline_guard)
            self._proofs[result["activations"][payload["activation_id"]]["sha256"]]=(context,)
            return result

    def grant(self,token,case_id,activation_id,recipient_token,*,ttl_seconds=20):
        integer(ttl_seconds,1,60)
        with self.review.identity._lock:
            context=self.authorization.access(token,case_id,"grant")
            state=self._state(context,case_id);activation=self._record(state,"activations",activation_id)
            recipient=activation["payload"]["recipient_id"]
            context=self.authorization.access(token,case_id,"grant",recipient)
            target=self.authorization.access(recipient_token,case_id,"receive",recipient)
            frame=self._activation_frame(context,activation);retained=self._proof(activation)
            guard=self._guard(context,frame,extra=(*retained,target),deadlines=((activation["recorded_at"],activation["payload"]["expires_at"]),))
            now=guard();expiry=min(now+ttl_seconds,activation["payload"]["expires_at"],context.identity.expires_at,target.identity.expires_at)
            if expiry<=now:
                _deny()
            payload={"grant_id":uuid.uuid4().hex,"activation_id":activation_id,"transfer_id":uuid.uuid4().hex,
                "recipient_id":recipient,"recipient_person_id":target.principal.person_id,
                "recipient_credential_sha256":target.credential_sha256,"expires_at":expiry,
                "max_attempted_bytes":3*activation["payload"]["artifact_size"]}
            final=self._guard(context,frame,extra=(*retained,target),deadlines=((now,expiry),))
            result=self.store.apply(case_id,"grant",payload,context.actor,expected_pin=self._pin,
                expected_head_sha256=state["head_sha256"],guard=final)
            self._accept(result["pin"],final)
            self._proofs[result["grants"][payload["grant_id"]]["sha256"]]=(context,target)
            return result

    def _manage(self,token,case_id,activation_id,action):
        with self.review.identity._lock:
            context=self.authorization.access(token,case_id,action)
            state=self._state(context,case_id);activation=self._record(state,"activations",activation_id)
            guard=context.recheck
            if action=="resume":
                frame=self._activation_frame(context,activation)
                guard=self._guard(context,frame,extra=self._proof(activation),
                    deadlines=((activation["recorded_at"],activation["payload"]["expires_at"]),))
            result=self.store.apply(case_id,action,{"activation_id":activation_id,"reason":"operator_request"},
                context.actor,expected_pin=self._pin,expected_head_sha256=state["head_sha256"],guard=guard)
            self._accept(result["pin"],guard)
            return result

    def suspend(self,token,case_id,activation_id):
        return self._manage(token,case_id,activation_id,"suspend")

    def resume(self,token,case_id,activation_id):
        return self._manage(token,case_id,activation_id,"resume")

    def revoke(self,token,case_id,activation_id):
        return self._manage(token,case_id,activation_id,"revoke")

    def revoke_grant(self,token,case_id,grant_id):
        with self.review.identity._lock:
            context=self.authorization.access(token,case_id,"revoke")
            state=self._state(context,case_id)
            result=self.store.apply(case_id,"revoke_grant",{"grant_id":grant_id},context.actor,
                expected_pin=self._pin,expected_head_sha256=state["head_sha256"],guard=context.recheck)
            self._accept(result["pin"],context.recheck)
            return result

    def deliver_chunk(self,token,case_id,activation_id,grant_id,transfer_id,offset,length,*,
                      request_id=None,chunk_id=None,writer):
        if not callable(writer):
            raise DeliveryError("A trusted bounded writer is required")
        with self.review.identity._lock:
            # Internal metadata discovery exposes no bytes or credentials.
            reader=self.review.authorization.access(token,case_id,"read")
            state=self._state(reader,case_id);activation=self._record(state,"activations",activation_id)
            context=self.authorization.access(token,case_id,"receive",activation["payload"]["recipient_id"])
            grant=self._record(state,"grants",grant_id)
            frame=self._activation_frame(context,activation)
            extras=(*self._proof(activation),*self._proof(grant))
            deadlines=((activation["recorded_at"],activation["payload"]["expires_at"]),
                (grant["recorded_at"],grant["payload"]["expires_at"]))
            guard=self._guard(context,frame,extra=extras,deadlines=deadlines)
            payload={"activation_id":activation_id,"grant_id":grant_id,"transfer_id":transfer_id,
                "request_id":uuid.uuid4().hex if request_id is None else request_id,
                "chunk_id":uuid.uuid4().hex if chunk_id is None else chunk_id,"offset":offset,"length":length}
            result=self.store._take_chunk(case_id,payload,context.actor,capability=self._capability,
                expected_pin=self._pin,expected_head_sha256=state["head_sha256"],guard=guard)
            self._accept(result["pin"],guard)
            content=result["bytes"];admission=result["admission"]
            if (type(content) is not bytes or len(content)!=admission["length"]
                    or hashlib.sha256(content).hexdigest()!=admission["chunk_sha256"]):
                raise StoreUnavailable("Admitted bytes changed")
            guard()  # Current checks after pin persistence and just before write.
            written=None;known=False;status="failed"
            try:
                actual=writer(content)
                if type(actual) is not int or not 0<=actual<=len(content):
                    raise DeliveryError("Writer extent is not known")
                written=actual;known=True;status="returned" if actual==len(content) else "interrupted"
            except Exception:
                # Bytes may already have escaped the trusted writer. Retain the
                # attempted admission; never report zero disclosure or receipt.
                pass
            observation={"request_id":admission["request_id"],"bytes_written":written,
                "status":status,"write_extent_known":known,"recipient_receipt_verified":False}
            recorded=False
            try:
                audit=self.store.get(case_id,expected_pin=self._pin,guard=self.review.identity._time)
                observed=self.store.apply(case_id,"observe",observation,context.actor,expected_pin=self._pin,
                    expected_head_sha256=audit["head_sha256"],guard=self.review.identity._time)
                self._accept(observed["pin"],self.review.identity._time);recorded=True
            except Exception:
                # Observation uncertainty cannot erase the durable admission.
                pass
            return {"admission":admission,"bytes_written":written,"status":status,"write_extent_known":known,
                "observation_recorded":recorded,"pin":self.required_pin,"public_fixture_bytes_delivered":known and written>0,
                "disclosure_may_have_occurred":not known or written>0,**FLAGS}

    def status(self,token,case_id):
        with self.review.identity._lock:
            context=self.authorization.access(token,case_id,"read")
            return self._state(context,case_id)
