from __future__ import annotations

import json
import unittest
from pathlib import Path

from model_release_assurance.analyzers.llm_watermark import LlmWatermarkAnalyzer
from model_release_assurance.analyzers.tree import TreeLinkageAnalyzer
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.integrity import canonical_json_bytes, sha256_bytes
from model_release_assurance.mcp_tools import AssuranceToolService
from model_release_assurance.models import AssessmentRequest, ReleaseContract, ThreatContract, TreeLinkageInput
from model_release_assurance.services import (
    AnalyzerServiceDescriptor,
    AnalyzerServiceRegistry,
    LocalAnalyzerService,
    McpAnalyzerService,
    ServiceTransport,
    default_analyzer_service_registry,
)


ROOT = Path(__file__).resolve().parents[1]


class AnalyzerServiceTests(unittest.TestCase):
    def test_default_registry_has_one_service_per_input_kind(self) -> None:
        registry = default_analyzer_service_registry()
        descriptors = registry.describe()
        kinds = [item.input_kind for item in descriptors]
        self.assertEqual(len(kinds), len(set(kinds)))
        self.assertIn("llm_watermark", kinds)
        self.assertIn("llm_canary", kinds)
        watermark = next(item for item in descriptors if item.input_kind == "llm_watermark")
        self.assertFalse(watermark.can_clear)
        self.assertFalse(watermark.can_block)

        capabilities = {
            item.input_kind: (item.can_clear, item.can_block)
            for item in descriptors
        }
        self.assertEqual(capabilities["tree_linkage"], (True, True))
        self.assertEqual(capabilities["dp"], (True, False))
        self.assertEqual(capabilities["finite_channel_ceiling"], (True, True))
        self.assertEqual(capabilities["attack"], (False, True))
        self.assertEqual(capabilities["attack_battery"], (False, True))
        self.assertEqual(capabilities["controlled_inference"], (False, True))
        self.assertEqual(capabilities["llm_canary"], (False, True))
        self.assertEqual(capabilities["llm_watermark"], (False, False))
        self.assertEqual(capabilities["population"], (False, False))

    def test_service_adapter_rejects_capability_widening(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot widen"):
            LocalAnalyzerService(LlmWatermarkAnalyzer(), can_clear=True)

    def test_duplicate_input_kind_is_rejected(self) -> None:
        first = LocalAnalyzerService(
            LlmWatermarkAnalyzer(), can_clear=False, can_block=False
        )
        second = LocalAnalyzerService(
            LlmWatermarkAnalyzer(), can_clear=False, can_block=False
        )
        second.descriptor = second.descriptor.model_copy(
            update={"service_id": "mra.analyzer.watermark-copy"}
        )
        with self.assertRaisesRegex(ValueError, "input kinds must be unique"):
            AnalyzerServiceRegistry((first, second))

    def test_mcp_adapter_uses_versioned_json_contract(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
        request = AssessmentRequest.model_validate(raw)
        analyzer_input = request.analyzer_inputs[0]
        calls = []

        def invoke(tool, payload):
            calls.append((tool, payload))
            return {"contract_version": "2.0", "evidence": [{
                "evidence_id": "remote",
                "threat_id": analyzer_input.threat_id,
                "analyzer": "tree_linkage",
                "producer": analyzer_input.provenance.producer.model_dump(mode="json"),
                **analyzer_input.evidence_context.model_dump(mode="json"),
                "evidence_class": "screen",
                "coverage": "screen_only",
                "metric": "remote_screen",
                "realizability": "not_applicable",
                "can_clear": False,
                "can_block": False,
            }]}

        service = McpAnalyzerService(
            AnalyzerServiceDescriptor(
                service_id=analyzer_input.provenance.producer.service_id,
                service_version=analyzer_input.provenance.producer.service_version,
                implementation_sha256=analyzer_input.provenance.producer.implementation_sha256,
                input_kind="tree_linkage",
                transport=ServiceTransport.MCP,
                mcp_tool="analyze_tree_linkage",
                can_clear=True,
                can_block=False,
            ),
            invoke,
        )
        records = service.analyze(request.release, request.threats[0], analyzer_input)
        self.assertEqual(len(records), 1)
        self.assertEqual(calls[0][0], "analyze_tree_linkage")
        self.assertEqual(calls[0][1]["contract_version"], "2.0")

    def test_mcp_discovery_exposes_service_capabilities(self) -> None:
        result = AssuranceToolService(ROOT).list_analyzer_services()
        self.assertEqual(result["contract_version"], "2.0")
        self.assertGreaterEqual(len(result["services"]), 7)
        self.assertTrue(all("mcp_tool" in item for item in result["services"]))

    def test_mcp_discovery_exposes_non_authorizing_red_team_tools(self) -> None:
        result = AssuranceToolService(ROOT).list_red_team_tools()
        self.assertEqual(result["contract_version"], "2.0")
        entries = result["catalog"]["entries"]
        self.assertEqual(
            {item["attack_id"] for item in entries},
            {"structural_disclosure", "worst_case_membership"},
        )
        self.assertTrue(all(not item["can_clear"] for item in entries))
        self.assertTrue(all(item["decision_authority"] == "none" for item in entries))
        self.assertEqual(len(result["catalog_sha256"]), 64)
        self.assertEqual(
            result["catalog_sha256"],
            sha256_bytes(canonical_json_bytes(result["catalog"])),
        )

    def test_mcp_validation_errors_do_not_echo_untrusted_input(self) -> None:
        sentinel = "secret-model-input-that-must-not-be-reflected"
        service = AssuranceToolService(ROOT)

        attack_result = service.validate_attack_battery({"payload": sentinel})
        request_result = service.validate_assessment_request({"payload": sentinel})

        self.assertFalse(attack_result["valid"])
        self.assertFalse(request_result["valid"])
        self.assertNotIn(sentinel, json.dumps(attack_result))
        self.assertNotIn(sentinel, json.dumps(request_result))

    def test_engine_rejects_remote_service_identity_escalation(self) -> None:
        raw = json.loads((ROOT / "examples" / "request.json").read_text(encoding="utf-8"))
        request = AssessmentRequest.model_validate(raw)

        def invoke(_tool, payload):
            release = ReleaseContract.model_validate(payload["release"])
            threat = ThreatContract.model_validate(payload["threat"])
            value = TreeLinkageInput.model_validate(payload["analyzer_input"])
            record = TreeLinkageAnalyzer().analyze(release, threat, value)[0]
            tampered = record.model_dump(mode="json")
            tampered["analyzer"] = "attack"
            return {"contract_version": "2.0", "evidence": [tampered]}

        remote = McpAnalyzerService(
            AnalyzerServiceDescriptor(
                service_id=request.analyzer_inputs[0].provenance.producer.service_id,
                service_version=request.analyzer_inputs[0].provenance.producer.service_version,
                implementation_sha256=request.analyzer_inputs[0].provenance.producer.implementation_sha256,
                input_kind="tree_linkage",
                transport=ServiceTransport.MCP,
                mcp_tool="analyze_tree_linkage",
                can_clear=True,
                can_block=True,
            ),
            invoke,
        )
        defaults = default_analyzer_service_registry().services
        registry = AnalyzerServiceRegistry((remote,) + tuple(
            service for service in defaults if service.descriptor.input_kind != "tree_linkage"
        ))
        with self.assertRaisesRegex(ValueError, "wrong analyzer identity"):
            AssuranceEngine(service_registry=registry).assess(request, ROOT / "examples")


if __name__ == "__main__":
    unittest.main()
