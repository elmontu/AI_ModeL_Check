"""Capture only fresh authenticated PRD17 executions for the delivery fixture.

This additive trusted driver preserves original implementations. There is no
attach/import API for caller paths, bytes, old registrations or approval claims.
"""
from __future__ import annotations

from pathlib import Path
import hashlib

from ..production_review.service import FixtureReviewService
from ..production_review.contracts import canonical_bytes
from ..production_identity.policy import PermissionDenied
from ..production_adapters import native


def _deny():
    raise PermissionDenied("Current original reviewed execution unavailable")


class DeliveryReviewBridge:
    def __init__(self,review):
        if type(review) is not FixtureReviewService:
            raise ValueError("The exact current review fixture is required")
        self.review=review
        self._sources={}

    def execute(self,token,case_id,campaign_id,*,output,data_root=None):
        with self.review.identity._lock:
            # The same original raw token is verified before and inside execute;
            # its immutable credential digest must equal the recorded start.
            context=self.review.authorization.access(token,case_id,"start")
            result=self.review.execute(token,case_id,campaign_id,output=output,data_root=data_root)
            campaign=result["campaigns"][campaign_id]
            if campaign["start"]["actor"]!=context.actor:
                _deny()
            context.recheck()
            self._sources[campaign_id]=(case_id,Path(output).absolute()/"native/candidate.json",context,
                campaign["start"]["sha256"],campaign["binding_sha256"])
            return result

    def prepare(self,context,campaign_id):
        """Trusted current review frame, never serialized as an authority proof."""
        with self.review.identity._lock:
            source=self._sources.get(campaign_id)
            if source is None or source[0]!=context.case.case_id:
                _deny()
            snapshot=self.review._case(context)
            campaign=self.review._campaign(snapshot,campaign_id)
            if (campaign["state"]!="completed" or campaign["start"]["sha256"]!=source[3]
                    or campaign["binding_sha256"]!=source[4]):
                _deny()
            participants=[source[2]]
            deadlines=[]
            for action,key in (("policy","policy_approval"),("assess","assessment"),("approve","approval")):
                decision=campaign[key]
                participants.extend(self.review._proof(decision,check=False))
                delegated=decision["payload"]["delegation_id"]
                if delegated is not None:
                    actor=self.review._proof(decision,check=False)[0]
                    participants.extend(self.review._delegation(snapshot,campaign,action,actor,delegated))
                    record=snapshot["delegations"][delegated]
                    deadlines.append((record["recorded_at"],record["payload"]["expires_at"]))
            if campaign["assessment"]["payload"]["verdict"]!="accept":
                _deny()
            observer=self.review._evidence.get(campaign_id)
            if observer is None:
                _deny()
            observer()
            deadlines.append(self.review._evidence_deadlines[campaign_id])
            artifact=native._read(source[1],2*1024*1024)
            if hashlib.sha256(artifact).hexdigest()!=campaign["completion"]["payload"]["candidate_sha256"]:
                _deny()
            # No current decision may infer authority from historical metadata.
            return {"campaign":campaign,"review_snapshot":snapshot,"artifact":artifact,
                "review_contexts":tuple(participants),"deadlines":tuple(deadlines)}

    def recheck_frame(self,context,frame):
        current=self.prepare(context,frame["campaign"]["policy"]["campaign_id"])
        if (canonical_bytes(current["campaign"])!=canonical_bytes(frame["campaign"])
                or current["review_snapshot"]["head_sha256"]!=frame["review_snapshot"]["head_sha256"]
                or current["artifact"]!=frame["artifact"]):
            _deny()
        return current
