"""Current signed policy approval around actual prospective public training.

Only this trusted in-process driver can attach completion evidence. Public
methods accept raw signed identities, fixed public profile selections and owned
review choices, never caller-authored admissions or candidate hashes. Persisted
metadata is historical; live verification contexts and retained evidence must
be established afresh after restart. Nothing here authorizes model delivery.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import uuid

from .authorization import ReviewAuthorization
from .contracts import FLAGS, ReviewError, canonical_bytes, digest, validate_policy
from .store import ReviewStore, StoreConflict
from ..production_identity.policy import FixtureIdentityService, PermissionDenied
from ..production_registration.workflow import LocalRegistrationWorkflow, prepare_native_input, workflow_sha256
from ..production_registration.profiles import load_profile
from ..production_registration.contracts import validate_registration, evaluate_native
from ..production_adapters import native
from ..production_adapters.contracts import strict_json as native_json
from ..production_evidence.replay import snapshot_native_bundle, artifact_manifest
from ..production_evidence.signing import verify_envelope
from ..production_evidence.verifier import runtime_observation
from ..production_evidence.contracts import (strict_json, validate_context, canonical_bytes as evidence_bytes, digest as evidence_digest)


def _deny():
    raise PermissionDenied("Current bound policy review unavailable")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class _ApprovedWorkflow(LocalRegistrationWorkflow):
    """Add current policy checks to every inherited prefit custody boundary."""
    def __init__(self, original, guard):
        super().__init__(original.registry, original.signer, original.store, original.evidence_ledger)
        self._approval_guard = guard

    def _current_key_time(self):
        self._approval_guard()
        return super()._current_key_time()


class FixtureReviewService:
    def __init__(self, identity, store, workflow):
        if (type(identity) is not FixtureIdentityService or type(store) is not ReviewStore
                or type(workflow) is not LocalRegistrationWorkflow):
            raise ReviewError("Review fixture bootstrap rejected")
        self.identity, self.store, self.workflow = identity, store, workflow
        self.authorization = ReviewAuthorization(identity)
        if identity._verifier.registry is not workflow.registry:
            raise ReviewError("Review fixture trust must be shared")
        self._proofs = {}
        self._evidence = {}
        self._evidence_deadlines = {}

    def _case(self, context):
        record = self.store.get(context.case.case_id, guard=context.recheck)
        for key in ("agency_id", "project_id", "case_id", "submitter_person_id"):
            if record["case"][key] != getattr(context.case, key):
                _deny()
        return record

    def _campaign(self, snapshot, campaign_id):
        if type(campaign_id) is not str or campaign_id not in snapshot["campaigns"]:
            raise StoreConflict("Review campaign unavailable")
        return snapshot["campaigns"][campaign_id]

    def _proof(self, record, *, check=True):
        if record is None or record["sha256"] not in self._proofs:
            _deny()
        contexts = self._proofs[record["sha256"]]
        if check:
            self.authorization.recheck_many(contexts)
        return contexts

    def _remember(self, record, contexts):
        self._proofs[record["sha256"]] = tuple(contexts)

    def _delegation(self, snapshot, campaign, action, context, delegation_id):
        if delegation_id is None:
            return ()
        record = snapshot["delegations"].get(delegation_id)
        if record is None or record["revoked"]:
            _deny()
        payload = record["payload"]
        if (payload["campaign_id"] != campaign["policy"]["campaign_id"]
                or payload["policy_sha256"] != campaign["policy_sha256"]
                or payload["action"] != action
                or payload["delegate_person_id"] != context.principal.person_id):
            _deny()
        contexts = self._proof(record)
        now = context.recheck()
        if not record["recorded_at"] <= now < payload["expires_at"]:
            _deny()
        return contexts

    def _current(self, context, campaign, *, evidence=False, assessment=False, snapshot=None,
                 extra=(), delegation_id=None, delegation_action=None):
        records=[campaign["policy_approval"]] + ([campaign["assessment"]] if assessment else [])
        participants=[context,*extra]
        deadlines=[]
        for record in records:
            participants.extend(self._proof(record,check=False))
            delegated=record["payload"]["delegation_id"]
            if delegated is not None:
                if snapshot is None or delegated not in snapshot["delegations"]:
                    _deny()
                delegation=snapshot["delegations"][delegated]
                if delegation["revoked"]:
                    _deny()
                deadlines.append(delegation)
        if delegation_id is not None:
            self._delegation(snapshot,campaign,delegation_action,context,delegation_id)
            deadlines.append(snapshot["delegations"][delegation_id])
        if evidence:
            observer=self._evidence.get(campaign["policy"]["campaign_id"])
            if observer is None:
                _deny()
            observer()
        now=self.authorization.recheck_many(participants)
        if evidence and not self._evidence_deadlines[campaign["policy"]["campaign_id"]][0]<=now<self._evidence_deadlines[campaign["policy"]["campaign_id"]][1]:
            _deny()
        if any(not record["recorded_at"]<=now<record["payload"]["expires_at"] for record in deadlines):
            _deny()
        return now

    def _inputs(self, policy, data_root):
        data = load_profile(policy["profile_id"], data_root=data_root, max_rows=policy["max_rows"])
        _, data_raw, plan_raw = prepare_native_input(data, policy["seed"])
        actual = {"source_sha256":data["source_sha256"], "data_sha256":_sha(data_raw),
            "metadata_sha256":digest(data["metadata"]), "plan_sha256":_sha(plan_raw),
            "workflow_sha256":workflow_sha256(), "runtime_sha256":digest(runtime_observation()),
            "adapter_sha256":native.implementation_sha256()}
        if any(actual[key] != policy[key] for key in actual):
            _deny()
        return actual

    def propose(self, token, case_id, *, profile_id="sklearn-wine", recipient_id="fixture-recipient",
                max_rows=128, seed=20261001, utility_floor_bps=0, max_membership_auc_bps=9900,
                data_root=None):
        with self.identity._lock:
            context = self.authorization.access(token, case_id, "propose")
            self._case(context)
            data = load_profile(profile_id, data_root=data_root, max_rows=max_rows)
            _, data_raw, plan_raw = prepare_native_input(data, seed)
            policy = validate_policy({"schema":"mra-fixture-review-policy/v1", "campaign_id":uuid.uuid4().hex,
                "agency_id":context.case.agency_id, "project_id":context.case.project_id, "case_id":case_id,
                "recipient_id":recipient_id, "profile_id":profile_id, "source_sha256":data["source_sha256"],
                "data_sha256":_sha(data_raw), "metadata_sha256":digest(data["metadata"]), "plan_sha256":_sha(plan_raw),
                "workflow_sha256":workflow_sha256(), "runtime_sha256":digest(runtime_observation()),
                "adapter_sha256":native.implementation_sha256(), "seed":seed, "max_rows":max_rows,
                "utility_floor_bps":utility_floor_bps, "max_membership_auc_bps":max_membership_auc_bps,
                "required_controls":["known_leak","null","loss_membership"], **FLAGS})
            snapshot=self._case(context)
            return self.store.apply(case_id,"propose",policy,context.actor,guard=context.recheck,expected_head_sha256=snapshot["head_sha256"])

    def approve_policy(self, token, case_id, campaign_id, delegation_id=None):
        with self.identity._lock:
            context = self.authorization.access(token,case_id,"policy")
            snapshot = self._case(context); campaign = self._campaign(snapshot,campaign_id)
            grantors = self._delegation(snapshot,campaign,"policy",context,delegation_id)
            def guard():
                self._delegation(snapshot,campaign,"policy",context,delegation_id)
                now=self.authorization.recheck_many((context,*grantors))
                if delegation_id is not None and not now<snapshot["delegations"][delegation_id]["payload"]["expires_at"]:
                    _deny()
                return now
            result = self.store.apply(case_id,"policy",{"campaign_id":campaign_id,
                "policy_sha256":campaign["policy_sha256"],"delegation_id":delegation_id},context.actor,guard=guard,expected_head_sha256=snapshot["head_sha256"])
            self._remember(result["campaigns"][campaign_id]["policy_approval"],(context,*grantors))
            return result

    def delegate(self,token,case_id,campaign_id,*,action,delegate_person_id,expires_at):
        with self.identity._lock:
            context = self.authorization.access(token,case_id,action)
            if "review:delegate" not in context.identity.scopes:
                _deny()
            snapshot = self._case(context); campaign = self._campaign(snapshot,campaign_id)
            payload={"delegation_id":uuid.uuid4().hex,"campaign_id":campaign_id,
                "policy_sha256":campaign["policy_sha256"],"action":action,
                "delegate_person_id":delegate_person_id,"expires_at":expires_at}
            result=self.store.apply(case_id,"delegate",payload,context.actor,guard=context.recheck,expected_head_sha256=snapshot["head_sha256"])
            self._remember(result["delegations"][payload["delegation_id"]],(context,))
            return result

    def revoke(self,token,case_id,delegation_id):
        with self.identity._lock:
            # Read only discovers the recorded role; its exact role and dedicated
            # delegation scope are then independently authenticated below.
            reader=self.authorization.access(token,case_id,"read")
            snapshot=self._case(reader); record=snapshot["delegations"].get(delegation_id)
            if record is None:
                _deny()
            context=self.authorization.access(token,case_id,record["payload"]["action"])
            if "review:delegate" not in context.identity.scopes:
                _deny()
            return self.store.apply(case_id,"revoke",{"delegation_id":delegation_id},context.actor,guard=context.recheck,expected_head_sha256=snapshot["head_sha256"])

    def execute(self,token,case_id,campaign_id,*,output,data_root=None):
        with self.identity._lock:
            context=self.authorization.access(token,case_id,"start")
            snapshot=self._case(context); campaign=self._campaign(snapshot,campaign_id)
            policy=campaign["policy"]
            def guard():
                self._inputs(policy,data_root)
                return self._current(context,campaign,snapshot=snapshot)
            guard()
            started=self.store.apply(case_id,"start",{"campaign_id":campaign_id,
                "policy_sha256":campaign["policy_sha256"]},context.actor,guard=guard,expected_head_sha256=snapshot["head_sha256"])
            campaign=started["campaigns"][campaign_id]
            try:
                run=_ApprovedWorkflow(self.workflow,guard).run(policy["profile_id"], output=output,
                    agency_id=policy["agency_id"],project_id=policy["project_id"],case_id=case_id,
                    data_root=data_root,max_rows=policy["max_rows"],seed=policy["seed"])
                if run["status"] != "review_recorded":
                    raise ReviewError("Registered execution did not complete")
                completion,observer=self._completion(Path(output),policy,context,guard,run)
                result=self.store.apply(case_id,"complete",completion,context.actor,guard=observer,expected_head_sha256=started["head_sha256"])
                self._evidence[campaign_id]=observer
                self._evidence_deadlines[campaign_id]=observer.evidence_lifetime
                return result
            except Exception:
                # Failure is permanent in the local trail; a stale credential
                # cannot authorize a new result or reset a started campaign.
                try:
                    self.store.apply(case_id,"fail",{"campaign_id":campaign_id,
                        "policy_sha256":campaign["policy_sha256"],"reason":"execution_failed"},
                        context.actor,guard=context.recheck)
                except Exception:
                    pass
                raise

    def _completion(self,output,policy,context,guard,run):
        names=("registration.json","registration-record.json","replay-envelope.json",
               "replay-admission.json","replay-context.json")
        captured={name:native._read(output/name,65536) for name in names}
        registration=validate_registration(strict_json(captured["registration.json"]))
        if (registration["registration_id"]!=run["registration_id"]
                or evidence_digest(registration)!=run["registration_sha256"]):
            _deny()
        evidence_context=validate_context(strict_json(captured["replay-context.json"]))
        for key in ("agency_id","project_id","case_id","profile_id"):
            if registration[key]!=policy[key]:
                _deny()
        for key in ("source_sha256","data_sha256","metadata_sha256"):
            if registration["source"][key]!=policy[key]:
                _deny()
        for key in ("plan_sha256","workflow_sha256","runtime_sha256"):
            if registration["plan"][key]!=policy[key]:
                _deny()
        if registration["plan"]["adapter_implementation_sha256"]!=policy["adapter_sha256"]:
            _deny()
        blobs=snapshot_native_bundle(output/"native")
        manifest=artifact_manifest(blobs)
        review=evaluate_native(registration,blobs)
        if evidence_bytes(review)!=evidence_bytes(run["review"]):
            _deny()
        admission=strict_json(captured["replay-admission.json"])
        verified=verify_envelope(captured["replay-envelope.json"],self.workflow.registry,
            self.workflow.profile,self.workflow.signer.registration.owner_id)
        if (canonical_bytes(verified["statement"]["context"])!=canonical_bytes(evidence_context)
                or verified["statement"]["artifacts"]!=manifest
                or evidence_context["job_id"]!=registration["registration_id"]
                or evidence_context["policy_sha256"]!=evidence_digest(registration)
                or admission["status"]!="accepted_local_replay"
                or admission["context_sha256"]!=digest(evidence_context)
                or admission["artifacts_sha256"]!=digest(manifest)
                or admission["envelope_sha256"]!=_sha(captured["replay-envelope.json"])):
            _deny()
        record=self.workflow.store.get(registration["registration_id"],guard=guard)
        if evidence_bytes(record)!=evidence_bytes(strict_json(captured["registration-record.json"])):
            _deny()
        expected_terminal={"registration_sha256":evidence_digest(registration),
            "artifacts_sha256":digest(manifest),"candidate_sha256":_sha(blobs["candidate.json"]),
            "report_sha256":_sha(blobs["report.json"]),
            "evidence_envelope_sha256":_sha(captured["replay-envelope.json"]),
            "evidence_admission_sha256":evidence_digest(admission),"review":review}
        if record["state"]!="completed" or evidence_bytes(record["completion"])!=evidence_bytes(expected_terminal):
            _deny()
        report=native_json(blobs["report.json"])
        if report["controls_passed"] is not True:
            _deny()
        gain=review["utility"]["improvement"]
        auc=report["membership"]["raw_auc"]
        # Conservative fixed integer comparison; raw report floats stay in its
        # retained original evidence, not in the exact policy/store contracts.
        gain_bps=max(-10000,min(10000,math.floor(gain*10000)))
        auc_bps=math.ceil(auc*10000) if auc>=0.5 else math.floor(auc*10000)
        completion={"campaign_id":policy["campaign_id"],"policy_sha256":digest(policy),
            "registration_id":registration["registration_id"],"registration_sha256":evidence_digest(registration),
            "candidate_sha256":_sha(blobs["candidate.json"]),"report_sha256":_sha(blobs["report.json"]),
            "artifacts_sha256":digest(manifest),"envelope_sha256":_sha(captured["replay-envelope.json"]),
            "admission_sha256":evidence_digest(admission),"context_sha256":digest(evidence_context),
            "utility_improvement_bps":gain_bps,"membership_auc_bps":auc_bps}
        def observer():
            guard()
            for name,raw in captured.items():
                if native._read(output/name,65536)!=raw:
                    _deny()
            if artifact_manifest(snapshot_native_bundle(output/"native"))!=manifest:
                _deny()
            current=verify_envelope(captured["replay-envelope.json"],self.workflow.registry,
                self.workflow.profile,self.workflow.signer.registration.owner_id)
            if current!=verified:
                _deny()
            if evidence_bytes(self.workflow.store.get(registration["registration_id"],guard=guard))!=evidence_bytes(record):
                _deny()
            now=guard()
            statement=verified["statement"]
            if not statement["issued_at"]<=now<statement["expires_at"]:
                _deny()
            return now
        observer.evidence_lifetime=(verified["statement"]["issued_at"],verified["statement"]["expires_at"])
        observer()
        return completion,observer

    def assess(self,token,case_id,campaign_id,*,verdict="accept",delegation_id=None):
        with self.identity._lock:
            context=self.authorization.access(token,case_id,"assess")
            snapshot=self._case(context); campaign=self._campaign(snapshot,campaign_id)
            grantors=self._delegation(snapshot,campaign,"assess",context,delegation_id)
            def guard():
                self._delegation(snapshot,campaign,"assess",context,delegation_id)
                return self._current(context,campaign,evidence=True,snapshot=snapshot,extra=grantors,delegation_id=delegation_id,delegation_action="assess")
            result=self.store.apply(case_id,"assess",{"campaign_id":campaign_id,
                "binding_sha256":campaign["binding_sha256"],"verdict":verdict,
                "delegation_id":delegation_id},context.actor,guard=guard,expected_head_sha256=snapshot["head_sha256"])
            self._remember(result["campaigns"][campaign_id]["assessment"],(context,*grantors))
            return result

    def approve(self,token,case_id,campaign_id,delegation_id=None):
        with self.identity._lock:
            context=self.authorization.access(token,case_id,"approve")
            snapshot=self._case(context); campaign=self._campaign(snapshot,campaign_id)
            grantors=self._delegation(snapshot,campaign,"approve",context,delegation_id)
            def guard():
                self._delegation(snapshot,campaign,"approve",context,delegation_id)
                return self._current(context,campaign,evidence=True,assessment=True,snapshot=snapshot,extra=grantors,delegation_id=delegation_id,delegation_action="approve")
            if campaign["assessment"] is None:
                _deny()
            result=self.store.apply(case_id,"approve",{"campaign_id":campaign_id,
                "binding_sha256":campaign["binding_sha256"],
                "assessment_sha256":campaign["assessment"]["sha256"],"delegation_id":delegation_id},
                context.actor,guard=guard,expected_head_sha256=snapshot["head_sha256"])
            self._remember(result["campaigns"][campaign_id]["approval"],(context,*grantors))
            return result

    def status(self,token,case_id,campaign_id):
        with self.identity._lock:
            context=self.authorization.access(token,case_id,"read")
            snapshot=self._case(context); campaign=self._campaign(snapshot,campaign_id)
            usable=False
            try:
                self._current(context,campaign,evidence=True,assessment=True,snapshot=snapshot)
                self._proof(campaign["approval"])
                # Delegation revocation is current durable state, not merely a
                # still-valid delegate token or cached grantor proof.
                for action,key in (("policy","policy_approval"),("assess","assessment"),("approve","approval")):
                    decision=campaign[key]
                    target=self._proof(decision)[0]
                    self._delegation(snapshot,campaign,action,target,decision["payload"]["delegation_id"])
                fresh=self._case(context)
                if fresh["head_sha256"] != snapshot["head_sha256"]:
                    _deny()
                participants=[context]
                delegations=[]
                for key in ("policy_approval","assessment","approval"):
                    decision=campaign[key]
                    participants.extend(self._proof(decision,check=False))
                    delegation_id=decision["payload"]["delegation_id"]
                    if delegation_id is not None:
                        delegations.append(snapshot["delegations"][delegation_id])
                now=self.authorization.recheck_many(participants)
                begin,end=self._evidence_deadlines[campaign_id]
                if (not begin<=now<end or any(not d["recorded_at"]<=now<d["payload"]["expires_at"] for d in delegations)):
                    _deny()
                usable=True
            except Exception:
                usable=False
            if not usable:
                context.recheck()
            return {"campaign":campaign,"reviews_usable":usable,**FLAGS}
