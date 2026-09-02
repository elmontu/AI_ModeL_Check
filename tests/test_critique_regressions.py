from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_release_assurance.decision import decide_threat
from model_release_assurance.models import (
    AssessmentRequest,
    AttackBatteryStatus,
    EvidenceClass,
    EvidenceConsistency,
    EvidenceCoverage,
    EvidenceRecord,
    Realizability,
    Verdict,
)


ROOT = Path(__file__).resolve().parents[1]


class ContradictoryEvidenceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
        cls.request = AssessmentRequest.model_validate(raw)
        cls.threat = next(
            threat for threat in cls.request.threats if threat.threat_id == "membership-person"
        )
        cls.scope = next(
            scope
            for scope in cls.request.population_scopes
            if scope.scope_id == cls.threat.population_scope_id
        )
        cls.context = next(
            value.evidence_context
            for value in cls.request.analyzer_inputs
            if value.threat_id == cls.threat.threat_id
        )
        cls.floor_producer = next(
            value.provenance.producer
            for value in cls.request.analyzer_inputs
            if value.analyzer == "attack"
        )
        cls.ceiling_producer = next(
            value.provenance.producer
            for value in cls.request.analyzer_inputs
            if value.analyzer == "dp"
        )

    def _floor(self, lower: float) -> EvidenceRecord:
        return EvidenceRecord(
            **self.context.model_dump(mode="python"),
            evidence_id="membership-floor",
            threat_id=self.threat.threat_id,
            analyzer="attack",
            producer=self.floor_producer,
            evidence_class=EvidenceClass.FLOOR,
            coverage=EvidenceCoverage.NAMED_PROJECTION,
            metric=self.threat.decision_metric,
            value=lower,
            lower=lower,
            realizability=Realizability.RECIPIENT,
            can_clear=False,
            can_block=True,
        )

    def _ceiling(self, upper: float) -> EvidenceRecord:
        return EvidenceRecord(
            **self.context.model_dump(mode="python"),
            evidence_id="membership-ceiling",
            threat_id=self.threat.threat_id,
            analyzer="dp",
            producer=self.ceiling_producer,
            evidence_class=EvidenceClass.CEILING,
            coverage=EvidenceCoverage.COMPLETE_INTERFACE,
            metric=self.threat.decision_metric,
            value=upper,
            upper=upper,
            realizability=Realizability.NOT_APPLICABLE,
            can_clear=True,
            can_block=False,
        )

    def _decide(self, records: tuple[EvidenceRecord, ...]):
        return decide_threat(
            self.threat,
            self.scope,
            self.request.release,
            records,
            self.request.policy.policy_sha256,
            AttackBatteryStatus(
                mode="required",
                requirement_id="regression-battery",
                required_attack_ids=("membership-loss-threshold",),
                completed_attack_ids=("membership-loss-threshold",),
                passing_positive_control_ids=("known-leak-control",),
                satisfied=True,
            ),
        )

    def test_contradictory_ceiling_cannot_weaken_blocking_floor(self) -> None:
        floor = self._floor(0.8)
        floor_only = self._decide((floor,))
        contradicted = self._decide((floor, self._ceiling(0.5)))

        self.assertEqual(floor_only.verdict, Verdict.BLOCK)
        self.assertEqual(floor_only.evidence_consistency, EvidenceConsistency.CONSISTENT)
        self.assertEqual(contradicted.verdict, Verdict.BLOCK)
        self.assertEqual(
            contradicted.evidence_consistency,
            EvidenceConsistency.CONTRADICTORY,
        )
        self.assertEqual(
            contradicted.conflicting_evidence_ids,
            ("membership-floor", "membership-ceiling"),
        )

    def test_nonblocking_contradiction_remains_inconclusive(self) -> None:
        decision = self._decide((self._floor(0.55), self._ceiling(0.5)))

        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(decision.evidence_consistency, EvidenceConsistency.CONTRADICTORY)
        self.assertEqual(
            decision.conflicting_evidence_ids,
            ("membership-floor", "membership-ceiling"),
        )

    def test_missing_decision_evidence_is_structurally_insufficient(self) -> None:
        decision = self._decide(())

        self.assertEqual(decision.verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(decision.evidence_consistency, EvidenceConsistency.INSUFFICIENT)
        self.assertEqual(decision.conflicting_evidence_ids, ())

    def test_binary64_boundary_is_an_explicit_conformance_gap(self) -> None:
        literal_boundary = self._decide((self._ceiling(0.6),))
        computed_boundary = self._decide((self._ceiling(0.2 + 0.4),))

        self.assertEqual(literal_boundary.verdict, Verdict.CLEAR)
        self.assertEqual(computed_boundary.verdict, Verdict.INCONCLUSIVE)
        self.assertGreater(0.2 + 0.4, 0.6)

    def test_excluded_evidence_is_named_in_the_decision(self) -> None:
        applicable = self._floor(0.7)
        excluded = applicable.model_copy(
            update={
                "evidence_id": "membership-excluded-wrong-metric",
                "metric": "incremental_bayes_linkage_success",
            }
        )

        decision = self._decide((applicable, excluded))

        self.assertEqual(decision.evidence_ids, ("membership-floor",))
        self.assertEqual(
            decision.excluded_evidence_ids,
            ("membership-excluded-wrong-metric",),
        )


if __name__ == "__main__":
    unittest.main()
