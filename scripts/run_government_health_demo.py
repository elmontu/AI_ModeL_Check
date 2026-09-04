#!/usr/bin/env python3
"""Run an offline, fictional government-health model-release demo suite.

The suite exercises the supported contract, assessment, optimization, signing,
audit, and protocol-replay code. Production-only registry, gateway, and
monitoring actions are represented by explicitly labelled mock records. No
network access, model training, or real personal data is used.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from model_release_assurance.audit import AuditStore
from model_release_assurance.engine import AssuranceEngine
from model_release_assurance.errors import AssuranceError
from model_release_assurance.experimental_workflow import run_experimental_workflow
from model_release_assurance.integrity import (
    build_signed_manifest,
    canonical_json_bytes,
    generate_ed25519_keypair,
    sha256_bytes,
    sha256_file,
    verify_signed_manifest,
)
from model_release_assurance.knowledge import KnowledgeIndex
from model_release_assurance.models import (
    AssessmentReport,
    AssessmentRequest,
    AttackBatteryWorkerOutput,
    OverallVerdict,
)
from model_release_assurance.optimizer import (
    OptimizationOutcome,
    OptimizationReport,
    OptimizationRequest,
    ReleaseOptimizer,
    build_signed_optimization_manifest,
    verify_signed_optimization_manifest,
)
from model_release_assurance.release_protocol import (
    ControlStatus,
    MonitoringOutcome,
    ReleaseProtocolActor,
    ReleaseProtocolArtifact,
    ReleaseProtocolArtifactKind,
    ReleaseProtocolEvent,
    ReleaseProtocolEventType,
    ReleaseProtocolRole,
    ReleaseProtocolRun,
    ReleaseProtocolState,
    ReleaseProtocolVerification,
    portfolio_registry_head_sha256,
    release_protocol_event_sha256,
    verify_release_protocol_run,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DEFAULT_OUTPUT_ROOT = ROOT / "output" / "government-health-demo"
MODEL_PREVIEW_MANIFEST = ROOT / "reproduction" / "model-audit-workflow" / "manifest.json"
MODEL_PREVIEW_MANIFEST_SHA256 = (
    "fcaedc885c8c099c3c41f373da4ff2cec4ea8c6be9a43a48f641b79bebb4e870"
)

# This closed inventory is the only material copied from the broad examples/
# directory. The pins make the suite's no-real-data statement independent of
# untracked files that may be present beside the examples.
DEMO_FIXTURE_SHA256 = {
    "request.json": "66f0622ce5671a2e8124f5ce4b9dca8ed2cf6a490d36c2b019f81aee1209f917",
    "optimization-request.json": "a122da96696974f83fe7915ffefb5f513ce6f8ce92217b22bfb7223d51f6681b",
    "policy.json": "33952cfe3632958fb82dc53d0035152af485547b7eab601c787f353f4fdedca0",
    "artifacts/demo-tree.json": "2f42b587627c5b6c4447d781b57a47082743f029b475f560a574553abcedfdd5",
    "config/tree-linkage-analyzer.json": "d462c2564b587a5429a5814e95f918003120cced4268db975a9fb6395a4715b3",
    "config/dp-analyzer.json": "f4d1c3ee56b6b9eddfa5b93e55400725dfdc3df92a3a652de4f09c0ad369e12c",
    "config/attack-analyzer.json": "a0e847216b048e8b180079c8c9ce33b684c5a826cf66ef0020ac793ee289b3a8",
    "config/attack-design-registration.json": "e42c2b5a00f2555f355a10fb4272022d14d5d141c42ab7afa5d61be50f442c83",
    "config/attack-battery-analyzer.json": "b48e0f7369e2c52b00c44ab917013c4dd7b80cadbd33bb81b623f76f0a1d927c",
    "evidence/tree-linkage.json": "3aed038499ee7cae81b67b483e024264117e78423528538a4a2e3288fafea79e",
    "evidence/dp-accountant.json": "94b6272e44832081a3f37a5be0743d820fdf2914fbe2d06a3c5261882dffe59c",
    "evidence/attack-counts.json": "5e026a5cc9a2e4e6d39e96ce08e7461449ce55f323b8189755fc6972bb703dd1",
    "evidence/attack-battery.json": "8a9c4dbd8c4814794c8f5658562f4b398a4d246742a3e0738885137d234ff4bd",
    "evidence/optimization-utility.json": "5b4023684dc651ef34ea37d18fd91433b9cdb3b706cf061b20bf7ce225af1e9b",
    "evidence/bounded-api-control.json": "095a53f4f80b6578c77155e81144fa9d8e782cd4efb52a0c69ee1c3956614c52",
    "evidence/bounded-api-portfolio.json": "8245d7ea28c7fb7460dcd6dfae26167e8e15b95a585bc320ea53f25ff677bc46",
    "evidence/portfolio-registry-snapshot.json": "2a73d705b33ea11f7b4446dfe27b14e4c07d0a7876babc2ef5fed35120b8c6d0",
}
MODEL_PROXY_DESCRIPTIONS = {
    "cnn": "hand-coded convolution/ReLU proxy over a tiny JSON artifact; not PyTorch, AlexNet, or DenseNet",
    "lstm": "hand-coded recurrent-cell proxy over a tiny JSON artifact; not a framework-trained LSTM",
    "xgboost": "hand-coded additive decision-stump proxy; the XGBoost library and a trained booster are not used",
    "llm": "hand-coded next-token lookup proxy; no pretrained or fine-tuned language model is used",
}

SUITE_ID = "fictional-government-health-release-demo"
SCENARIO_ORDER = (
    "controlled_candidate",
    "missing_evidence",
    "demonstrated_leakage",
    "artifact_tamper",
    "mock_full_lifecycle",
    "stale_registry",
    "deployment_mismatch",
    "monitoring_incident",
)
PIPELINE_STAGE_ORDER = (
    "model_execution_preview",
    "training_export_handoff",
    "contract_validation",
    "evidence_assessment",
    "controlled_optimization",
    "signature_verification",
    "audit_replay_and_checkpoint",
    "external_handoff",
)

ROLE_GUIDE = (
    {
        "role": "Programme owner",
        "example_actor": "Government health programme team",
        "responsibility": "Freeze the intended use, recipients, prohibited uses, and accountable owner.",
    },
    {
        "role": "Clinical authority",
        "example_actor": "Government clinical safety lead",
        "responsibility": "Review clinical validity, workflow effects, escalation, and patient-impact safeguards.",
    },
    {
        "role": "Data steward",
        "example_actor": "Private hospital data office",
        "responsibility": "Approve lawful data use and the exact population snapshot; never upload patient data to this demo.",
    },
    {
        "role": "Evidence and privacy team",
        "example_actor": "Independent model-assurance unit",
        "responsibility": "Freeze the evidence plan, run approved tests, and explain floors, ceilings, and gaps.",
    },
    {
        "role": "Authorization authority",
        "example_actor": "Government accountable officer",
        "responsibility": "Make the external, reasoned governance decision after independent review.",
    },
    {
        "role": "Registry and gateway operators",
        "example_actor": "Health AI registry and serving platform",
        "responsibility": "Atomically record authorization and serve only the exact approved bytes, interface, and controls.",
    },
    {
        "role": "Monitoring and incident teams",
        "example_actor": "Clinical operations and incident authority",
        "responsibility": "Watch agreed indicators and suspend, revoke, or expire access when required.",
    },
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_model(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        value.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _copy_examples(destination: Path, source_root: Path = EXAMPLES) -> None:
    """Copy only the pre-audited synthetic fixture inventory."""
    if destination.exists():
        raise FileExistsError(f"demo fixture destination already exists: {destination}")
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("demo fixture source root must be a real directory")
    resolved_root = source_root.resolve(strict=True)
    sources: list[tuple[Path, Path, str]] = []
    for relative_text, expected_sha256 in DEMO_FIXTURE_SHA256.items():
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe pinned fixture path: {relative_text}")
        source = source_root / relative
        cursor = source_root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError(f"demo fixture cannot be a symlink: {relative_text}")
        try:
            resolved_source = source.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"missing pinned demo fixture: {relative_text}") from exc
        if not resolved_source.is_relative_to(resolved_root) or not source.is_file():
            raise ValueError(f"invalid pinned demo fixture: {relative_text}")
        actual_sha256 = sha256_file(source)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"pinned demo fixture digest mismatch: {relative_text}"
            )
        sources.append((source, relative, expected_sha256))

    destination.mkdir(parents=True)
    for source, relative, expected_sha256 in sources:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256_file(target) != expected_sha256:
            raise RuntimeError(f"copied demo fixture digest mismatch: {relative}")


def _attack_battery(raw: dict[str, Any]) -> dict[str, Any]:
    return next(
        value
        for value in raw["analyzer_inputs"]
        if value["analyzer"] == "attack_battery"
    )


def _rehash_worker_output(battery: dict[str, Any]) -> None:
    output = AttackBatteryWorkerOutput.model_validate(battery["worker_output"])
    battery["worker_output_sha256"] = sha256_bytes(canonical_json_bytes(output))


def _materialize_analyzer_sources(
    raw: dict[str, Any],
    fixture_root: Path,
) -> AssessmentRequest:
    """Write exact scenario payloads without modifying tracked examples."""
    parsed = AssessmentRequest.model_validate(raw)
    resolved_root = fixture_root.resolve(strict=True)
    for claimed, value in zip(raw["analyzer_inputs"], parsed.analyzer_inputs, strict=True):
        declared_source = Path(claimed["provenance"]["source_path"])
        if declared_source.is_absolute():
            raise ValueError("demo analyzer source path must be relative")
        source = (resolved_root / declared_source).resolve(strict=False)
        if not source.is_relative_to(resolved_root):
            raise ValueError("demo analyzer source path escapes its copied fixture directory")
        _write_json(
            source,
            value.model_dump(mode="json", exclude={"provenance"}, exclude_none=False),
        )
        claimed["provenance"]["source_sha256"] = sha256_file(source)
    return AssessmentRequest.model_validate(raw)


def _run_assessment(
    request: AssessmentRequest,
    fixture_root: Path,
    audit: AuditStore,
) -> AssessmentReport:
    intent = audit.append_assessment_intent(request)
    try:
        report = AssuranceEngine().assess(request, fixture_root)
    except Exception as exc:
        audit.append_assessment_failed(intent, type(exc).__name__, str(exc)[:4096])
        raise
    audit.append_assessment_completed(intent, report)
    return report


def _run_optimization(
    request: OptimizationRequest,
    fixture_root: Path,
    audit: AuditStore,
) -> OptimizationReport:
    intent = audit.append_optimization_intent(request)
    try:
        report = ReleaseOptimizer().optimize(request, fixture_root)
    except Exception as exc:
        audit.append_optimization_failed(intent, type(exc).__name__, str(exc)[:4096])
        raise
    audit.append_optimization_completed(intent, report)
    return report


def _threat_summary(report: AssessmentReport) -> list[dict[str, Any]]:
    return [
        {
            "threat_id": decision.threat_id,
            "decision": decision.verdict.value,
            "operational_gate": decision.resolution.release_gate,
            "metric": str(decision.decision_metric),
            "tolerance": decision.tolerance,
            "lower_bound": decision.lower_bound,
            "upper_bound": decision.upper_bound,
            "next_actions": list(decision.resolution.actions),
            "missing_obligations": list(decision.resolution.missing_obligations),
        }
        for decision in report.decisions
    ]


def _assessment_scenario(
    *,
    scenario_id: str,
    report: AssessmentReport,
    report_path: Path,
    run_dir: Path,
    expected_decision: str,
    next_actor: str,
    next_action: str,
) -> dict[str, Any]:
    translation = {
        OverallVerdict.CLEAR: "CONTINUE_TO_EXTERNAL_REVIEW",
        OverallVerdict.INCONCLUSIVE: "HOLD",
        OverallVerdict.BLOCK: "BLOCK_AND_REDESIGN",
    }[report.overall_verdict]
    if translation != expected_decision:
        raise RuntimeError(
            f"scenario {scenario_id} produced {translation}, expected {expected_decision}"
        )
    return {
        "scenario_id": scenario_id,
        "execution_scope": "live_reference_core",
        "result": translation,
        "expected_result": expected_decision,
        "passed": True,
        "stop_stage": (
            "external_authorization"
            if report.overall_verdict is OverallVerdict.CLEAR
            else "assessment"
        ),
        "assessment_verdict": report.overall_verdict.value,
        "optimization_outcome": None,
        "protocol_final_state": None,
        "authorization_recorded_in_mock_transcript": False,
        "production_authorization_issued": False,
        "deployment_active": False,
        "what_happened": {
            "CONTINUE_TO_EXTERNAL_REVIEW": (
                "The scoped threat checks passed for this exact candidate and interface."
            ),
            "HOLD": "Evidence could not support a decision, so the candidate stopped.",
            "BLOCK_AND_REDESIGN": (
                "A validated attack floor exceeded policy tolerance, so the candidate stopped."
            ),
        }[translation],
        "who_owns_next": next_actor,
        "next_action": next_action,
        "what_this_does_not_prove": (
            "This assessment does not prove legal compliance, clinical validity, general safety, "
            "live-interface conformance, or authorization."
        ),
        "threats": _threat_summary(report),
        "artifacts": [
            {
                "kind": "assessment_report_v5",
                "path": report_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(report_path),
            }
        ],
    }


def _make_artifact(
    *,
    bundle_dir: Path,
    artifact_id: str,
    kind: ReleaseProtocolArtifactKind,
    producer_actor_id: str,
    content: bytes,
) -> ReleaseProtocolArtifact:
    path = Path("artifacts") / f"{artifact_id.replace(':', '-')}.json"
    destination = bundle_dir / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return ReleaseProtocolArtifact(
        artifact_id=artifact_id,
        kind=kind,
        path=path.as_posix(),
        sha256=sha256_file(destination),
        producer_actor_id=producer_actor_id,
    )


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _workflow_actors() -> tuple[ReleaseProtocolActor, ...]:
    organizations = {
        ReleaseProtocolRole.MODEL_OWNER: "Private hospital model team (fictional)",
        ReleaseProtocolRole.POLICY_AUTHORITY: "Government health AI policy office (fictional)",
        ReleaseProtocolRole.POPULATION_STEWARD: "Private hospital data office (fictional)",
        ReleaseProtocolRole.CONFIGURATION_GENERATOR: "Government release engineering (fictional)",
        ReleaseProtocolRole.EVIDENCE_AUTHORITY: "Independent evidence laboratory (fictional)",
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR: "Government model assurance unit (fictional)",
        ReleaseProtocolRole.OPTIMIZATION_AUTHORITY: "Government optimization authority (fictional)",
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY: "Government accountable officer (fictional)",
        ReleaseProtocolRole.PORTFOLIO_REGISTRY: "Mock health AI registry",
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY: "Mock health API gateway",
        ReleaseProtocolRole.MONITORING_AUTHORITY: "Mock clinical monitoring service",
        ReleaseProtocolRole.INCIDENT_AUTHORITY: "Mock health incident authority",
    }
    return tuple(
        ReleaseProtocolActor(
            actor_id=f"demo:{role.value}",
            role=role,
            organization=organizations[role],
            key_id=f"demo-unsigned:{role.value}",
        )
        for role in ReleaseProtocolRole
    )


def _build_workflow_bundle(
    *,
    bundle_dir: Path,
    request: AssessmentRequest,
    assessment: AssessmentReport,
    assessment_path: Path,
    optimization: OptimizationReport,
    optimization_path: Path,
    policy_path: Path,
    reference_time: datetime,
) -> dict[str, Any]:
    bundle_dir.mkdir(parents=True, exist_ok=False)
    boundary_notice_path = bundle_dir / "00-DEMO-ONLY-NOT-AUTHORIZED.md"
    boundary_notice_path.write_text(
        "\n".join(
            [
                "# DEMO ONLY — NOT AUTHORIZED — NOT ACTIVE",
                "",
                "Every JSON file in this directory is a fictional structural workflow",
                "rehearsal. No external authority, registry, gateway, or monitoring service",
                "was contacted or changed.",
                "",
                "Raw MRAP transcript and verification fields such as",
                "`authorization_issued=true`, `deployment_active=true`, or `ACTIVE` describe",
                "only the state recorded by a supplied mock transcript. They are not claims",
                "about a production model. Read `../START-HERE.md` for the decision boundary.",
                "",
                "The healthcare scenario is a discussion overlay. The live reference core",
                "assessed the separate generic synthetic fixture identified in the suite",
                "report; it did not assess a healthcare model or healthcare evidence.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    actors = _workflow_actors()
    actor_ids = {actor.role: actor.actor_id for actor in actors}
    artifacts: dict[str, ReleaseProtocolArtifact] = {}

    def add_artifact(
        name: str,
        kind: ReleaseProtocolArtifactKind,
        role: ReleaseProtocolRole,
        value: Any,
        *,
        canonical: bool = False,
        source: Path | None = None,
    ) -> ReleaseProtocolArtifact:
        if source is not None:
            content = source.read_bytes()
        elif canonical:
            content = canonical_json_bytes(value)
        else:
            content = _json_bytes(value)
        artifact = _make_artifact(
            bundle_dir=bundle_dir,
            artifact_id=f"demo:{name}",
            kind=kind,
            producer_actor_id=actor_ids[role],
            content=content,
        )
        artifacts[name] = artifact
        return artifact

    add_artifact(
        "registration",
        ReleaseProtocolArtifactKind.REGISTRATION,
        ReleaseProtocolRole.MODEL_OWNER,
        {
            "demo_only": True,
            "release_id": request.release.release_id,
            "intended_use": request.release.purpose,
            "executed_contract_owner": request.release.owner,
            "executed_contract_recipient": request.release.recipient,
            "healthcare_discussion_overlay_executed_by_core": False,
            "training_handoff": "pre-built synthetic demonstration artifact",
        },
    )
    policy_artifact = add_artifact(
        "policy-snapshot",
        ReleaseProtocolArtifactKind.POLICY_SNAPSHOT,
        ReleaseProtocolRole.POLICY_AUTHORITY,
        None,
        source=policy_path,
    )
    release_instance = add_artifact(
        "release-instance",
        ReleaseProtocolArtifactKind.RELEASE_INSTANCE,
        ReleaseProtocolRole.CONFIGURATION_GENERATOR,
        request.release,
        canonical=True,
    )
    add_artifact(
        "population-register",
        ReleaseProtocolArtifactKind.POPULATION_REGISTER,
        ReleaseProtocolRole.POPULATION_STEWARD,
        {
            "demo_only": True,
            "contains_real_personal_data": False,
            "population_scopes": [
                value.model_dump(mode="json", exclude_none=False)
                for value in request.population_scopes
            ],
        },
    )
    add_artifact(
        "threat-register",
        ReleaseProtocolArtifactKind.THREAT_REGISTER,
        ReleaseProtocolRole.POLICY_AUTHORITY,
        {
            "demo_only": True,
            "threats": [
                value.model_dump(mode="json", exclude_none=False)
                for value in request.threats
            ],
        },
    )
    add_artifact(
        "portfolio-snapshot",
        ReleaseProtocolArtifactKind.PORTFOLIO_SNAPSHOT,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "registry_head_sha256": optimization.portfolio_registry_head_sha256,
            "registry_sequence": optimization.portfolio_registry_sequence,
        },
    )
    add_artifact(
        "evidence-plan",
        ReleaseProtocolArtifactKind.EVIDENCE_PLAN,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        {
            "demo_only": True,
            "plan": "replay every pre-bound demonstration analyzer input",
            "warning": "this is not healthcare evidence and was not generated during training",
        },
    )
    add_artifact(
        "assurance-error-budget",
        ReleaseProtocolArtifactKind.ASSURANCE_ERROR_BUDGET,
        ReleaseProtocolRole.POLICY_AUTHORITY,
        {"demo_only": True, "alpha_budget": "0.05", "alpha_spent": "0.04"},
    )
    add_artifact(
        "monitoring-plan",
        ReleaseProtocolArtifactKind.MONITORING_PLAN,
        ReleaseProtocolRole.MONITORING_AUTHORITY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "indicators": ["input drift", "output distribution", "clinical override rate"],
            "incident_action": "suspend access pending human review",
        },
    )
    add_artifact(
        "evidence-bundle",
        ReleaseProtocolArtifactKind.EVIDENCE_BUNDLE,
        ReleaseProtocolRole.EVIDENCE_AUTHORITY,
        {
            "demo_only": True,
            "assessment_request_sha256": assessment.request_sha256,
            "evidence_ids": [value.evidence_id for value in assessment.evidence],
        },
    )
    assessment_artifact = add_artifact(
        "assessment-report",
        ReleaseProtocolArtifactKind.ASSESSMENT_REPORT,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        None,
        source=assessment_path,
    )
    optimization_artifact = add_artifact(
        "optimization-report",
        ReleaseProtocolArtifactKind.OPTIMIZATION_REPORT,
        ReleaseProtocolRole.OPTIMIZATION_AUTHORITY,
        None,
        source=optimization_path,
    )
    add_artifact(
        "authorization-request",
        ReleaseProtocolArtifactKind.AUTHORIZATION_COMMIT_REQUEST,
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "decision": "fictional approval for workflow rehearsal only",
            "controls": list(optimization.selected_control_ids),
        },
    )
    add_artifact(
        "authorization-receipt",
        ReleaseProtocolArtifactKind.AUTHORIZATION_RECEIPT,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
        {"demo_only": True, "mock_external_record": True, "recorded": True},
    )
    portfolio_commit = add_artifact(
        "portfolio-commit",
        ReleaseProtocolArtifactKind.PORTFOLIO_COMMIT,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "release_id": request.release.release_id,
            "selected_configuration_id": optimization.selected_configuration_id,
        },
    )
    add_artifact(
        "activation-receipt",
        ReleaseProtocolArtifactKind.ACTIVATION_RECEIPT,
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "served_artifact_sha256": optimization.selected_release_artifact_sha256,
            "served_interface_sha256": optimization.selected_release_interface_sha256,
        },
    )
    add_artifact(
        "incident-record",
        ReleaseProtocolArtifactKind.INCIDENT_RECORD,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
        {
            "demo_only": True,
            "mock_external_record": True,
            "reason": "fictional post-activation monitoring alert",
        },
    )

    if policy_artifact.sha256 != assessment.policy_sha256:
        raise RuntimeError("workflow policy artifact does not match the assessed policy")
    if release_instance.sha256 != assessment.release_contract_sha256:
        raise RuntimeError("workflow release instance does not match the assessed contract")
    if optimization.selected_release_artifact_sha256 is None:
        raise RuntimeError("controlled demo did not select a release artifact")
    if optimization.selected_release_interface_sha256 is None:
        raise RuntimeError("controlled demo did not select a release interface")
    if optimization.selected_configuration_id is None:
        raise RuntimeError("controlled demo did not select a configuration")

    def event_sequence(
        specifications: list[
            tuple[
                ReleaseProtocolEventType,
                ReleaseProtocolRole,
                tuple[ReleaseProtocolArtifact, ...],
                dict[str, Any],
            ]
        ],
    ) -> tuple[ReleaseProtocolEvent, ...]:
        events: list[ReleaseProtocolEvent] = []
        for event_type, role, event_artifacts, payload in specifications:
            sequence = len(events) + 1
            previous = release_protocol_event_sha256(events[-1]) if events else None
            events.append(
                ReleaseProtocolEvent(
                    sequence=sequence,
                    event_id=f"demo:event:{sequence}:{event_type.value}",
                    event_type=event_type,
                    occurred_at=reference_time + timedelta(minutes=sequence),
                    actor_id=actor_ids[role],
                    actor_role=role,
                    previous_event_sha256=previous,
                    artifacts=event_artifacts,
                    **payload,
                )
            )
        return tuple(events)

    common = [
        (
            ReleaseProtocolEventType.REGISTER_SCOPE,
            ReleaseProtocolRole.MODEL_OWNER,
            (
                artifacts["registration"],
                artifacts["policy-snapshot"],
                artifacts["release-instance"],
                artifacts["population-register"],
                artifacts["threat-register"],
                artifacts["portfolio-snapshot"],
            ),
            {},
        ),
        (
            ReleaseProtocolEventType.APPROVE_EVIDENCE_PLAN,
            ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
            (
                artifacts["evidence-plan"],
                artifacts["assurance-error-budget"],
                artifacts["monitoring-plan"],
            ),
            {"assurance_alpha_budget": Decimal("0.05")},
        ),
    ]
    evidence_complete = (
        ReleaseProtocolEventType.CLOSE_EVIDENCE,
        ReleaseProtocolRole.EVIDENCE_AUTHORITY,
        (artifacts["evidence-bundle"],),
        {
            "mandatory_evidence_complete": True,
            "selection_coverage_valid": True,
            "positive_control_status": ControlStatus.PASS,
            "assurance_alpha_spent": Decimal("0.04"),
        },
    )
    assessed = (
        ReleaseProtocolEventType.RECORD_ASSESSMENT,
        ReleaseProtocolRole.INDEPENDENT_ASSESSOR,
        (assessment_artifact,),
        {"assessment_verdict": assessment.overall_verdict},
    )
    selected = (
        ReleaseProtocolEventType.RECORD_SELECTION,
        ReleaseProtocolRole.OPTIMIZATION_AUTHORITY,
        (optimization_artifact,),
        {
            "optimization_outcome": optimization.outcome,
            "selected_configuration_id": optimization.selected_configuration_id,
        },
    )
    authorization_expiry = reference_time + timedelta(days=30)
    authorization_request = (
        ReleaseProtocolEventType.SUBMIT_AUTHORIZATION,
        ReleaseProtocolRole.AUTHORIZATION_AUTHORITY,
        (artifacts["authorization-request"],),
        {"authorization_expires_at": authorization_expiry},
    )
    committed_sequence = optimization.portfolio_registry_sequence + 1
    committed_head = portfolio_registry_head_sha256(
        previous_head_sha256=optimization.portfolio_registry_head_sha256,
        committed_sequence=committed_sequence,
        release_id=request.release.release_id,
        release_instance_sha256=assessment.release_contract_sha256,
        portfolio_commit_sha256=portfolio_commit.sha256,
    )
    commit = (
        ReleaseProtocolEventType.COMMIT_PORTFOLIO,
        ReleaseProtocolRole.PORTFOLIO_REGISTRY,
        (artifacts["authorization-receipt"], portfolio_commit),
        {
            "expected_registry_head_sha256": optimization.portfolio_registry_head_sha256,
            "committed_registry_head_sha256": committed_head,
            "expected_registry_sequence": optimization.portfolio_registry_sequence,
            "committed_registry_sequence": committed_sequence,
            "atomic_compare_and_swap_succeeded": True,
        },
    )
    activation = (
        ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT,
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
        (artifacts["activation-receipt"],),
        {
            "deployed_artifact_sha256": optimization.selected_release_artifact_sha256,
            "deployed_interface_sha256": optimization.selected_release_interface_sha256,
        },
    )

    base_run = {
        "protocol_id": "MRAP/1.0",
        "release_id": request.release.release_id,
        "release_instance_sha256": assessment.release_contract_sha256,
        "artifact_sha256": optimization.selected_release_artifact_sha256,
        "interface_sha256": optimization.selected_release_interface_sha256,
        "policy_sha256": assessment.policy_sha256,
        "population_scope_sha256s": assessment.population_scope_sha256s,
        "registered_portfolio_head_sha256": optimization.portfolio_registry_head_sha256,
        "registered_portfolio_sequence": optimization.portfolio_registry_sequence,
        "actors": actors,
    }

    runs: dict[str, ReleaseProtocolRun] = {}
    runs["mock_full_lifecycle"] = ReleaseProtocolRun(
        **base_run,
        events=event_sequence(
            [*common, evidence_complete, assessed, selected, authorization_request, commit, activation]
        ),
        claimed_state=ReleaseProtocolState.ACTIVE,
    )
    stale_specifications = [
        *common,
        evidence_complete,
        assessed,
        selected,
        authorization_request,
        (
            ReleaseProtocolEventType.COMMIT_PORTFOLIO,
            ReleaseProtocolRole.PORTFOLIO_REGISTRY,
            (artifacts["authorization-receipt"], portfolio_commit),
            {
                "expected_registry_head_sha256": optimization.portfolio_registry_head_sha256,
                "committed_registry_head_sha256": committed_head,
                "expected_registry_sequence": optimization.portfolio_registry_sequence,
                "committed_registry_sequence": committed_sequence,
                "atomic_compare_and_swap_succeeded": False,
            },
        ),
    ]
    runs["stale_registry"] = ReleaseProtocolRun(
        **base_run,
        events=event_sequence(stale_specifications),
        claimed_state=ReleaseProtocolState.COMMIT_PENDING,
    )

    mismatch_activation = (
        ReleaseProtocolEventType.ACTIVATE_DEPLOYMENT,
        ReleaseProtocolRole.DEPLOYMENT_GATEWAY,
        (artifacts["activation-receipt"],),
        {
            "deployed_artifact_sha256": "f" * 64,
            "deployed_interface_sha256": optimization.selected_release_interface_sha256,
        },
    )
    runs["deployment_mismatch"] = ReleaseProtocolRun(
        **base_run,
        events=event_sequence(
            [
                *common,
                evidence_complete,
                assessed,
                selected,
                authorization_request,
                commit,
                mismatch_activation,
            ]
        ),
        claimed_state=ReleaseProtocolState.AUTHORIZED,
    )

    suspension = (
        ReleaseProtocolEventType.SUSPEND_RELEASE,
        ReleaseProtocolRole.INCIDENT_AUTHORITY,
        (artifacts["incident-record"],),
        {"reason": "fictional monitoring alert requires clinical and privacy review"},
    )
    runs["monitoring_incident"] = ReleaseProtocolRun(
        **base_run,
        events=event_sequence(
            [
                *common,
                evidence_complete,
                assessed,
                selected,
                authorization_request,
                commit,
                activation,
                suspension,
            ]
        ),
        claimed_state=ReleaseProtocolState.SUSPENDED,
    )

    verification_time = reference_time + timedelta(minutes=20)
    verifications: dict[str, ReleaseProtocolVerification] = {}
    for scenario_id, run in runs.items():
        transcript_path = bundle_dir / f"{scenario_id}-release-protocol-run.json"
        _write_model(transcript_path, run)
        verification = verify_release_protocol_run(
            run,
            bundle_dir,
            verify_artifact_files=True,
            as_of=verification_time,
        )
        _write_model(
            bundle_dir / f"{scenario_id}-release-protocol-verification.json",
            verification,
        )
        verifications[scenario_id] = verification

    return {
        "runs": runs,
        "verifications": verifications,
        "bundle_dir": bundle_dir,
        "boundary_notice_path": boundary_notice_path,
    }


def _workflow_scenario(
    *,
    scenario_id: str,
    workflow: dict[str, Any],
    run_dir: Path,
    result: str,
    expected_valid: bool,
    expected_state: ReleaseProtocolState,
    next_actor: str,
    next_action: str,
) -> dict[str, Any]:
    verification: ReleaseProtocolVerification = workflow["verifications"][scenario_id]
    run: ReleaseProtocolRun = workflow["runs"][scenario_id]
    if verification.valid is not expected_valid:
        raise RuntimeError(
            f"workflow scenario {scenario_id} validity was {verification.valid}, "
            f"expected {expected_valid}"
        )
    if verification.final_state is not expected_state:
        raise RuntimeError(
            f"workflow scenario {scenario_id} ended {verification.final_state.value}, "
            f"expected {expected_state.value}"
        )
    bundle_dir: Path = workflow["bundle_dir"]
    transcript_path = bundle_dir / f"{scenario_id}-release-protocol-run.json"
    verification_path = (
        bundle_dir / f"{scenario_id}-release-protocol-verification.json"
    )
    boundary_notice_path: Path = workflow["boundary_notice_path"]
    return {
        "scenario_id": scenario_id,
        "execution_scope": "synthetic_external_workflow_rehearsal",
        "result": result,
        "expected_result": result,
        "passed": True,
        "stop_stage": {
            "mock_full_lifecycle": "mock_active",
            "stale_registry": "commit_pending",
            "deployment_mismatch": "mock_gateway",
            "monitoring_incident": "mock_suspended",
        }[scenario_id],
        "assessment_verdict": (
            "clear" if len(run.events) >= 4 else None
        ),
        "optimization_outcome": (
            "release_with_controls" if len(run.events) >= 5 else None
        ),
        "protocol_final_state": verification.final_state.value,
        "protocol_valid": verification.valid,
        "protocol_profile": verification.verification_profile.value,
        "artifact_files_verified": verification.artifact_files_verified,
        "protocol_degradations": sorted(value.value for value in verification.degradations),
        "authorization_recorded_in_mock_transcript": verification.authorization_issued,
        "production_authorization_issued": False,
        "deployment_active": False,
        "mock_transcript_records_active": verification.deployment_active,
        "what_happened": {
            "mock_full_lifecycle": (
                "Mock registry and gateway records formed a structurally consistent ACTIVE transcript."
            ),
            "stale_registry": (
                "The mock atomic registry update failed, so no authorization was recorded."
            ),
            "deployment_mismatch": (
                "The gateway presented different model bytes and protocol replay rejected activation."
            ),
            "monitoring_incident": (
                "A fictional incident authority suspended the mock active release."
            ),
        }[scenario_id],
        "who_owns_next": next_actor,
        "next_action": next_action,
        "what_this_does_not_prove": (
            "The verifier replays supplied records. It does not perform external authorization, "
            "authenticate these structural-profile actors, validate every receipt semantically, "
            "deploy a model, or operate monitoring."
        ),
        "verification_reasons": list(verification.reasons),
        "artifacts": [
            {
                "kind": "demo_workflow_boundary_notice",
                "path": boundary_notice_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(boundary_notice_path),
            },
            {
                "kind": "release_protocol_run_v1_1",
                "path": transcript_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(transcript_path),
            },
            {
                "kind": "release_protocol_verification_v2",
                "path": verification_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(verification_path),
            },
        ],
    }


def _validate_suite_report(report: dict[str, Any]) -> None:
    if report.get("demo_only") is not True:
        raise ValueError("demo suite must declare demo_only=true")
    if report.get("contains_real_personal_data") is not False:
        raise ValueError("demo suite must declare that it contains no real personal data")
    if report.get("production_authorization_issued") is not False:
        raise ValueError("demo suite cannot issue production authorization")
    if report.get("training_executed") is not False:
        raise ValueError("this demo must not claim to execute model training")
    fixture_inventory = report.get("fixture_inventory", {})
    if (
        fixture_inventory.get("closed_allowlist") is not True
        or fixture_inventory.get("source_directory_copied_wholesale") is not False
        or fixture_inventory.get("files") != DEMO_FIXTURE_SHA256
    ):
        raise ValueError("demo suite must expose the exact pinned fixture inventory")
    executed_contract = report.get("executed_contract", {})
    discussion_overlay = report.get("fictional_healthcare_discussion_overlay", {})
    if (
        executed_contract.get("healthcare_specific") is not False
        or discussion_overlay.get("executed_by_live_reference_core") is not False
    ):
        raise ValueError("demo suite must keep the healthcare overlay separate")
    preview_models = report.get("model_execution_preview", {}).get("models", [])
    if not preview_models or any(
        value.get("framework_model_executed") is not False
        or value.get("can_clear") is not False
        for value in preview_models
    ):
        raise ValueError("model previews must remain disclosed, non-clearing proxies")
    scenarios = report.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("demo suite scenarios must be a list")
    ids = tuple(value.get("scenario_id") for value in scenarios)
    if ids != SCENARIO_ORDER:
        raise ValueError(f"demo suite scenario order changed: {ids}")
    if any(value.get("production_authorization_issued") is not False for value in scenarios):
        raise ValueError("a demo scenario cannot issue production authorization")
    if any(value.get("passed") is not True for value in scenarios):
        raise ValueError("every demo scenario must match its registered expectation")
    operational_spine = report.get("operational_spine")
    if not isinstance(operational_spine, dict):
        raise ValueError("demo suite must expose its contract, pipeline, and workflow")
    pipeline = operational_spine.get("pipeline", {})
    if tuple(pipeline.get("stage_order", ())) != PIPELINE_STAGE_ORDER:
        raise ValueError("demo pipeline stage order changed")
    workflow = operational_spine.get("workflow", {})
    if workflow.get("production_state_changed") is not False:
        raise ValueError("demo workflow cannot claim a production state change")
    if workflow.get("boundary_notice") != (
        "workflow-rehearsal/00-DEMO-ONLY-NOT-AUTHORIZED.md"
    ):
        raise ValueError("demo workflow must expose its adjacent non-authorization notice")


def _render_markdown(report: dict[str, Any]) -> str:
    scenarios = report["scenarios"]
    lines = [
        "# Government health model-release guided demo",
        "",
        "> **DEMO ONLY — FICTIONAL RECORDS — NO REAL PATIENT DATA — NOT AUTHORIZED.**",
        "",
        "This report explains what the current MRA reference implementation checked and",
        "where a government agency still needs real people and production systems.",
        "",
        "## Two deliberately separate cases",
        "",
        "- **Discussion overlay (not executed):** a government agency considers",
        "  clinician-reviewed 30-day readmission outreach using private-hospital data.",
        "  It never automates denial of care, insurance, or a public service.",
        "- **Live executable fixture:** the checked-in generic synthetic contract",
        f"  `{report['executed_contract']['release_id']}` for",
        f"  `{report['executed_contract']['purpose']}`. It contains no healthcare data.",
        "",
        "The live result belongs only to the generic fixture. It must not be presented as",
        "evidence about a readmission model or transferred to the healthcare discussion case.",
        "",
        "## Result at a glance",
        "",
        "The live core found that the controlled **generic synthetic** candidate may continue",
        "to external review. MRA did **not** authorize or activate it. Mock lifecycle records",
        "teach the hand-offs and failure branches; they do not change production state.",
        "",
        "| Scenario | Scope | Result | Stop or hand-off | Next owner |",
        "|---|---|---|---|---|",
    ]
    for scenario in scenarios:
        lines.append(
            "| {scenario_id} | {execution_scope} | **{result}** | {stop_stage} | {who_owns_next} |".format(
                **scenario
            )
        )

    lines.extend(["", "## Decision cards"])
    for scenario in scenarios:
        lines.extend(
            [
                "",
                f"### `{scenario['scenario_id']}` — {scenario['result']}",
                "",
                f"- **What happened:** {scenario['what_happened']}",
                f"- **Next owner:** {scenario['who_owns_next']}",
                f"- **Next action:** {scenario['next_action']}",
                f"- **What this does not prove:** {scenario['what_this_does_not_prove']}",
            ]
        )

    lines.extend(
        [
            "",
            "## What the live pipeline did",
            "",
            "1. **Proxy preview and training/export hand-off:** executed four hand-coded",
            "   functional proxies over tiny synthetic JSON artifacts, all explicitly",
            "   non-clearing, then checked the SHA-256 digest of the separate synthetic model",
            "   artifact referenced by the assessment contract.",
            "   The suite did not train a model or admit preview output as assessment evidence.",
            "2. **Contract:** validated the generic synthetic release, policy, population,",
            "   threat, evidence, artifact, and interface fields.",
            "3. **Assessment pipeline:** replayed the bound analyzers and converted evidence",
            "   into per-threat `CLEAR`, `HOLD`, or `BLOCK` gates.",
            "4. **Optimization pipeline:** selected the bounded API and its named control only",
            "   after privacy, utility, portfolio, and information-minimality gates passed.",
            "5. **Integrity:** signed and verified the assessment and optimization reports,",
            "   then replayed the hash-chained audit ledger.",
            "6. **Workflow:** replayed fictional registry, gateway, and monitoring transcripts",
            "   to demonstrate valid and fail-closed state transitions.",
            "   Raw transcript booleans describe mock state only; see",
            "   `workflow-rehearsal/00-DEMO-ONLY-NOT-AUTHORIZED.md`.",
            "",
            "### What the four preview labels actually mean",
            "",
            "| Label | Implementation used in this demo | Framework model executed? |",
            "|---|---|---|",
        ]
    )
    for model in report["model_execution_preview"]["models"]:
        lines.append(
            f"| {model['kind']} | {model['implementation_disclosure']} | "
            f"{str(model['framework_model_executed']).lower()} |"
        )

    lines.extend(
        [
            "",
            "## What each result means",
            "",
            "- **CONTINUE_TO_EXTERNAL_REVIEW:** scoped checks passed for the exact candidate;",
            "  the accountable authority, registry, gateway, clinical review, and legal review",
            "  are still required.",
            "- **HOLD:** evidence is incomplete or cannot support a decision. Do not release.",
            "- **BLOCK_AND_REDESIGN:** a demonstrated risk exceeded tolerance. Redesign or reject.",
            "- **STOP:** an integrity or deployment mismatch was found. Do not proceed.",
            "- **REASSESS:** the registry state changed. Refresh the portfolio snapshot and rerun",
            "  every affected stage.",
            "- **SIMULATED_ACTIVE / SIMULATED_SUSPENDED:** these labels describe mock records,",
            "  not a model deployed or authorized by MRA.",
            "",
            "## Healthcare discussion-overlay roles",
            "",
            "| Role | Example actor | Responsibility |",
            "|---|---|---|",
        ]
    )
    for role in report["role_guide"]:
        lines.append(
            f"| {role['role']} | {role['example_actor']} | {role['responsibility']} |"
        )

    controlled = next(
        value for value in scenarios if value["scenario_id"] == "controlled_candidate"
    )
    lines.extend(
        [
            "",
            "## Controlled-candidate metrics",
            "",
            "A lower bound above tolerance can block. A valid complete-interface upper bound",
            "at or below tolerance can clear that one frozen threat. An interval crossing the",
            "tolerance is a hold. A weak or unsuccessful attack never proves safety.",
            "",
            "| Threat | Metric | Lower | Upper | Tolerance | Gate |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for threat in controlled["threats"]:
        lines.append(
            f"| {threat['threat_id']} | {threat['metric']} | "
            f"{threat['lower_bound']:.6f} | {threat['upper_bound']:.6f} | "
            f"{threat['tolerance']:.6f} | {threat['operational_gate']} |"
        )

    lines.extend(
        [
            "",
            "## Audit artifacts",
            "",
            f"- Audit ledger events: `{report['audit']['event_count']}`",
            f"- Audit ledger complete: `{str(report['audit']['complete']).lower()}`",
            f"- Audit head: `{report['audit']['head_sha256']}`",
            f"- Assessment signature verified: `{str(report['integrity']['assessment_signature_verified']).lower()}`",
            f"- Optimization signature verified: `{str(report['integrity']['optimization_signature_verified']).lower()}`",
            "- The temporary private signing key was not retained after normal completion.",
            "",
            "## Hard limits",
            "",
            "- The executed contract, model artifact, and evidence are generic synthetic fixtures,",
            "  not a healthcare contract or healthcare validation.",
            "- Training, data-rights review, clinical validation, fairness evaluation, and live",
            "  production controls are outside this run.",
            "- Structural transcript replay does not authenticate the fictional actors.",
            "- The verifier does not establish semantic completeness of an external registry delta.",
            "- MRA recommendations, signatures, and replay results are not authorization.",
            "",
            "For the operational procedure and discussion prompts, read",
            "`docs/guided-government-health-demo.md` in the repository.",
            "",
        ]
    )
    return "\n".join(lines)


def run_demo_suite(
    run_dir: Path,
    *,
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    """Execute every registered scenario and return the non-authorizing report."""
    resolved_run_dir = run_dir.resolve(strict=False)
    for input_root in (EXAMPLES, MODEL_PREVIEW_MANIFEST.parent):
        resolved_input_root = input_root.resolve(strict=True)
        if resolved_run_dir == resolved_input_root or resolved_run_dir.is_relative_to(
            resolved_input_root
        ):
            raise ValueError(
                f"demo run directory cannot be inside input tree: {input_root}"
            )
    if run_dir.exists():
        raise FileExistsError(
            f"refusing to mix demo runs in existing directory: {run_dir}"
        )
    started_at = reference_time or datetime.now(timezone.utc)
    if started_at.utcoffset() is None:
        raise ValueError("reference_time must include a timezone offset")
    run_dir.mkdir(parents=True)
    fixture_parent = run_dir / "fixtures"
    reports_dir = run_dir / "reports"
    reports_dir.mkdir()
    audit = AuditStore(run_dir / "audit" / "mra.sqlite3")

    if MODEL_PREVIEW_MANIFEST.is_symlink() or not MODEL_PREVIEW_MANIFEST.is_file():
        raise ValueError("model-preview manifest must be a regular, non-symlink file")
    if sha256_file(MODEL_PREVIEW_MANIFEST) != MODEL_PREVIEW_MANIFEST_SHA256:
        raise ValueError("model-preview manifest failed its pinned digest")
    model_preview = run_experimental_workflow(
        MODEL_PREVIEW_MANIFEST,
        # The guided suite does not index the ambient workspace, so arbitrary
        # local documents cannot enter its no-real-data output boundary.
        knowledge_index=KnowledgeIndex(()),
    )
    if model_preview["decision"] != "no_release_authorization":
        raise RuntimeError("synthetic model preview exceeded its non-authorizing scope")
    if any(value["can_clear"] is not False for value in model_preview["models"]):
        raise RuntimeError("synthetic model preview unexpectedly emitted clearing evidence")
    for value in model_preview["models"]:
        value["implementation_disclosure"] = MODEL_PROXY_DESCRIPTIONS[value["kind"]]
        value["framework_model_executed"] = False
    model_preview_path = reports_dir / "model-execution-preview.json"
    _write_json(model_preview_path, model_preview)

    # Scenario A: real reference-core assessment and a genuinely joined
    # assessment -> optimization hand-off over copied synthetic fixtures.
    controlled_root = fixture_parent / "controlled-candidate"
    _copy_examples(controlled_root)
    controlled_raw = json.loads(
        (controlled_root / "request.json").read_text(encoding="utf-8")
    )
    controlled_request = AssessmentRequest.model_validate(controlled_raw)
    controlled_artifact = controlled_root / controlled_request.release.artifact_path
    actual_artifact_sha256 = sha256_file(controlled_artifact)
    if actual_artifact_sha256 != controlled_request.release.artifact_sha256:
        raise RuntimeError("training/export hand-off artifact failed its declared digest")
    controlled_report = _run_assessment(controlled_request, controlled_root, audit)
    controlled_report_path = reports_dir / "controlled-assessment.json"
    _write_model(controlled_report_path, controlled_report)
    copied_assessment_path = controlled_root / "evidence" / "generated-assessment.json"
    shutil.copyfile(controlled_report_path, copied_assessment_path)

    optimization_raw = json.loads(
        (controlled_root / "optimization-request.json").read_text(encoding="utf-8")
    )
    assessment_reference = optimization_raw["configurations"][0]["assessment"]
    assessment_reference["report_path"] = "evidence/generated-assessment.json"
    assessment_reference["report_sha256"] = sha256_file(copied_assessment_path)
    controlled_optimization_request = OptimizationRequest.model_validate(
        optimization_raw
    )
    controlled_optimization_request_path = (
        controlled_root / "generated-optimization-request.json"
    )
    _write_model(
        controlled_optimization_request_path,
        controlled_optimization_request,
    )
    controlled_optimization = _run_optimization(
        controlled_optimization_request,
        controlled_root,
        audit,
    )
    controlled_optimization_path = reports_dir / "controlled-optimization.json"
    _write_model(controlled_optimization_path, controlled_optimization)

    controlled_scenario = _assessment_scenario(
        scenario_id="controlled_candidate",
        report=controlled_report,
        report_path=controlled_report_path,
        run_dir=run_dir,
        expected_decision="CONTINUE_TO_EXTERNAL_REVIEW",
        next_actor="External accountable authority and relevant domain authority",
        next_action=(
            "Review the named bounded-API control and all external legal, domain, "
            "registry, and gateway obligations; do not deploy from this report."
        ),
    )
    if controlled_optimization.outcome is not OptimizationOutcome.RELEASE_WITH_CONTROLS:
        raise RuntimeError("controlled scenario did not select release_with_controls")
    controlled_scenario.update(
        {
            "optimization_outcome": controlled_optimization.outcome.value,
            "selected_configuration_id": controlled_optimization.selected_configuration_id,
            "selected_control_ids": list(controlled_optimization.selected_control_ids),
            "authorization_eligible": controlled_optimization.authorization_eligible,
        }
    )
    controlled_scenario["artifacts"].append(
        {
            "kind": "optimization_report_v4",
            "path": controlled_optimization_path.relative_to(run_dir).as_posix(),
            "sha256": sha256_file(controlled_optimization_path),
        }
    )

    # Scenario B: a live core HOLD caused by a failed mandatory positive control.
    missing_root = fixture_parent / "missing-evidence"
    _copy_examples(missing_root)
    missing_raw = json.loads(
        (missing_root / "request.json").read_text(encoding="utf-8")
    )
    missing_battery = _attack_battery(missing_raw)
    positive_control = missing_battery["worker_output"]["positive_controls"][0]
    positive_control.update(
        status="failed",
        successes=None,
        trials=None,
        reported_detection_lower_bound=None,
        expected_flag_observed=None,
    )
    _rehash_worker_output(missing_battery)
    missing_request = _materialize_analyzer_sources(missing_raw, missing_root)
    _write_model(missing_root / "generated-request.json", missing_request)
    missing_report = _run_assessment(missing_request, missing_root, audit)
    missing_report_path = reports_dir / "missing-evidence-assessment.json"
    _write_model(missing_report_path, missing_report)
    missing_scenario = _assessment_scenario(
        scenario_id="missing_evidence",
        report=missing_report,
        report_path=missing_report_path,
        run_dir=run_dir,
        expected_decision="HOLD",
        next_actor="Independent evidence and privacy team",
        next_action=(
            "Repair the approved positive control, rerun the frozen evidence family, "
            "and submit a fresh hash-bound evidence bundle."
        ),
    )

    # Scenario C: a live core BLOCK caused by a strong, policy-valid attack floor.
    leakage_root = fixture_parent / "demonstrated-leakage"
    _copy_examples(leakage_root)
    leakage_raw = json.loads(
        (leakage_root / "request.json").read_text(encoding="utf-8")
    )
    standalone = next(
        value
        for value in leakage_raw["analyzer_inputs"]
        if value["analyzer"] == "attack"
    )
    standalone["successes"] = 900
    leakage_battery = _attack_battery(leakage_raw)
    leakage_battery["worker_output"]["results"][0]["successes"] = 900
    _rehash_worker_output(leakage_battery)
    leakage_request = _materialize_analyzer_sources(leakage_raw, leakage_root)
    _write_model(leakage_root / "generated-request.json", leakage_request)
    leakage_report = _run_assessment(leakage_request, leakage_root, audit)
    leakage_report_path = reports_dir / "demonstrated-leakage-assessment.json"
    _write_model(leakage_report_path, leakage_report)
    leakage_scenario = _assessment_scenario(
        scenario_id="demonstrated_leakage",
        report=leakage_report,
        report_path=leakage_report_path,
        run_dir=run_dir,
        expected_decision="BLOCK_AND_REDESIGN",
        next_actor="Model owner, relevant domain authority, and privacy team",
        next_action=(
            "Stop release, redesign the model or interface, retrain if necessary, "
            "and begin a new bound assessment."
        ),
    )

    # Scenario D: a real digest failure before assessment. The audit ledger keeps
    # only a redacted diagnostic fingerprint.
    tamper_root = fixture_parent / "artifact-tamper"
    _copy_examples(tamper_root)
    tamper_request = AssessmentRequest.model_validate_json(
        (tamper_root / "request.json").read_text(encoding="utf-8")
    )
    tampered_artifact = tamper_root / tamper_request.release.artifact_path
    tampered_artifact.write_bytes(tampered_artifact.read_bytes() + b"\n")
    tamper_intent = audit.append_assessment_intent(tamper_request)
    tamper_error = ""
    try:
        AssuranceEngine().assess(tamper_request, tamper_root)
    except (AssuranceError, OSError, ValueError) as exc:
        tamper_error = str(exc)
        audit.append_assessment_failed(
            tamper_intent,
            type(exc).__name__,
            tamper_error[:4096],
        )
    else:
        raise RuntimeError("tampered artifact unexpectedly reached assessment")
    if "artifact hash mismatch" not in tamper_error:
        raise RuntimeError(f"unexpected tamper failure: {tamper_error}")
    tamper_scenario = {
        "scenario_id": "artifact_tamper",
        "execution_scope": "live_reference_core",
        "result": "STOP",
        "expected_result": "STOP",
        "passed": True,
        "stop_stage": "training_export_handoff",
        "assessment_verdict": None,
        "optimization_outcome": None,
        "protocol_final_state": None,
        "authorization_recorded_in_mock_transcript": False,
        "production_authorization_issued": False,
        "deployment_active": False,
        "what_happened": (
            "The model bytes no longer matched the contract digest, so assessment did not run."
        ),
        "who_owns_next": "Model owner and configuration generator",
        "next_action": (
            "Quarantine the artifact, determine why it changed, create a new release instance, "
            "and repeat evidence collection."
        ),
        "what_this_does_not_prove": (
            "Digest mismatch detects changed bytes; it does not identify intent or prove "
            "the untampered model is acceptable."
        ),
        "failure_category": "artifact_hash_mismatch",
        "artifacts": [],
    }

    # Integrity demonstrations over the two actual pipeline reports.
    public_key = run_dir / "integrity" / "demo-only-public-key.pem"
    with tempfile.TemporaryDirectory(prefix="mra-demo-signing-") as temporary:
        private_key = Path(temporary) / "private.pem"
        temporary_public_key = Path(temporary) / "public.pem"
        generate_ed25519_keypair(private_key, temporary_public_key)
        assessment_manifest = build_signed_manifest(
            controlled_report,
            controlled_request,
            private_key,
        )
        verify_signed_manifest(
            assessment_manifest,
            controlled_report,
            temporary_public_key,
        )
        optimization_manifest = build_signed_optimization_manifest(
            controlled_optimization,
            private_key,
        )
        verify_signed_optimization_manifest(
            optimization_manifest,
            controlled_optimization,
            temporary_public_key,
        )
        public_key.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary_public_key, public_key)
    assessment_manifest_path = run_dir / "integrity" / "assessment-manifest.json"
    _write_model(assessment_manifest_path, assessment_manifest)
    optimization_manifest_path = run_dir / "integrity" / "optimization-manifest.json"
    _write_model(optimization_manifest_path, optimization_manifest)

    workflow = _build_workflow_bundle(
        bundle_dir=run_dir / "workflow-rehearsal",
        request=controlled_request,
        assessment=controlled_report,
        assessment_path=controlled_report_path,
        optimization=controlled_optimization,
        optimization_path=controlled_optimization_path,
        policy_path=controlled_root / "policy.json",
        reference_time=started_at,
    )
    mock_full = _workflow_scenario(
        scenario_id="mock_full_lifecycle",
        workflow=workflow,
        run_dir=run_dir,
        result="SIMULATED_ACTIVE",
        expected_valid=True,
        expected_state=ReleaseProtocolState.ACTIVE,
        next_actor="Real authorization, registry, gateway, and clinical operations teams",
        next_action=(
            "Replace every mock receipt with authenticated production records and independently "
            "verify the live endpoint; this demo result cannot be promoted."
        ),
    )
    stale_registry = _workflow_scenario(
        scenario_id="stale_registry",
        workflow=workflow,
        run_dir=run_dir,
        result="REASSESS",
        expected_valid=False,
        expected_state=ReleaseProtocolState.COMMIT_PENDING,
        next_actor="Portfolio registry and model owner",
        next_action=(
            "Refresh the registry snapshot, rebase the candidate, and rerun all affected "
            "portfolio, assessment, and authorization steps."
        ),
    )
    deployment_mismatch = _workflow_scenario(
        scenario_id="deployment_mismatch",
        workflow=workflow,
        run_dir=run_dir,
        result="STOP",
        expected_valid=False,
        expected_state=ReleaseProtocolState.AUTHORIZED,
        next_actor="Deployment gateway and incident authority",
        next_action=(
            "Refuse activation, quarantine the mismatched bundle, and investigate before any retry."
        ),
    )
    monitoring_incident = _workflow_scenario(
        scenario_id="monitoring_incident",
        workflow=workflow,
        run_dir=run_dir,
        result="SIMULATED_SUSPENDED",
        expected_valid=True,
        expected_state=ReleaseProtocolState.SUSPENDED,
        next_actor="Clinical, privacy, and incident authorities",
        next_action=(
            "Keep access suspended while the fictional alert is investigated; revoke, expire, "
            "or reassess before any restart."
        ),
    )

    audit_verification = audit.verify(require_events=True)
    audit_checkpoint = audit.export_checkpoint(require_events=True)
    audit_checkpoint_path = run_dir / "audit" / "checkpoint.json"
    _write_model(audit_checkpoint_path, audit_checkpoint)
    with sqlite3.connect(audit.path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "demo_only": True,
        "contains_real_personal_data": False,
        "network_access_required": False,
        "training_executed": False,
        "fixture_inventory": {
            "closed_allowlist": True,
            "source_directory_copied_wholesale": False,
            "file_count": len(DEMO_FIXTURE_SHA256),
            "files": dict(DEMO_FIXTURE_SHA256),
            "model_preview_manifest_sha256": MODEL_PREVIEW_MANIFEST_SHA256,
            "statement": (
                "Only these pre-audited, digest-pinned synthetic files are read into "
                "scenario workspaces; unrelated files under examples/ are ignored."
            ),
        },
        "training_handoff": {
            "status": "verified_existing_synthetic_artifact",
            "artifact_sha256": actual_artifact_sha256,
            "statement": (
                "The demo begins at model export. Real training and training-hook evidence "
                "admission are outside this suite."
            ),
        },
        "model_execution_preview": {
            "status": "completed_nonclearing_functional_proxy_screen",
            "models": [
                {
                    "experiment_id": value["experiment_id"],
                    "kind": value["kind"],
                    "purpose": value["purpose"],
                    "implementation_disclosure": value["implementation_disclosure"],
                    "framework_model_executed": value["framework_model_executed"],
                    "functional_metric": value["functional_evaluation"]["metric"],
                    "functional_value": value["functional_evaluation"]["value"],
                    "can_clear": value["can_clear"],
                }
                for value in model_preview["models"]
            ],
            "admitted_to_assessment": False,
            "admission_join_status": "not_implemented",
            "statement": (
                "The preview proves only that hand-coded proxies over tiny synthetic JSON "
                "artifacts executed. It did not run framework-trained models and is not "
                "training evidence, privacy evidence, healthcare validation, or authorization."
            ),
            "artifact": {
                "kind": "experimental_model_workflow_v1",
                "path": model_preview_path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(model_preview_path),
            },
        },
        "executed_contract": {
            "release_id": controlled_request.release.release_id,
            "owner": controlled_request.release.owner,
            "recipient": controlled_request.release.recipient,
            "purpose": controlled_request.release.purpose,
            "model_family": controlled_request.release.model_family,
            "protected_unit": controlled_request.release.protected_unit,
            "artifact_sha256": controlled_request.release.artifact_sha256,
            "interface_sha256": sha256_bytes(
                canonical_json_bytes(controlled_request.release.interface)
            ),
            "healthcare_specific": False,
            "relationship_to_healthcare_overlay": (
                "separate generic synthetic fixture used to demonstrate mechanics; its "
                "results do not transfer to the discussion scenario"
            ),
        },
        "fictional_healthcare_discussion_overlay": {
            "owner": "Government health agency",
            "data_provider": "Private hospitals",
            "purpose": "clinician-reviewed 30-day readmission outreach",
            "prohibited_use": "automated denial of treatment, insurance, or public services",
            "executed_by_live_reference_core": False,
            "reason": (
                "teaches accountable roles and hand-offs without claiming that the generic "
                "fixture is healthcare evidence"
            ),
        },
        "production_authorization_issued": False,
        "default_conclusion": (
            "OFFLINE REFERENCE CHECKS COMPLETE — EXTERNAL GOVERNANCE AND LIVE-GATEWAY "
            "CHECKS REQUIRED — NOT AUTHORIZED — NOT ACTIVE"
        ),
        "operational_spine": {
            "contract": {
                "status": "valid",
                "assessment_request_schema": controlled_request.schema_version,
                "assessment_report_schema": controlled_report.schema_version,
                "optimization_request_schema": controlled_optimization_request.schema_version,
                "optimization_report_schema": controlled_optimization.schema_version,
                "executed_release_id": controlled_request.release.release_id,
                "healthcare_overlay_executed": False,
                "meaning": (
                    "defines the exact generic synthetic candidate, evidence, policy, and "
                    "interface used by the live core"
                ),
            },
            "pipeline": {
                "execution": "live_reference_core",
                "stage_order": list(PIPELINE_STAGE_ORDER),
                "stages": [
                    {
                        "stage": "model_execution_preview",
                        "status": "completed_nonclearing",
                        "owner": "model team",
                    },
                    {
                        "stage": "training_export_handoff",
                        "status": "artifact_digest_verified",
                        "owner": "model owner and configuration generator",
                    },
                    {
                        "stage": "contract_validation",
                        "status": "valid",
                        "owner": "programme owner and policy authority",
                    },
                    {
                        "stage": "evidence_assessment",
                        "status": controlled_report.overall_verdict.value,
                        "owner": "independent assessor",
                    },
                    {
                        "stage": "controlled_optimization",
                        "status": controlled_optimization.outcome.value,
                        "owner": "optimization authority",
                    },
                    {
                        "stage": "signature_verification",
                        "status": "demo_signatures_verified",
                        "owner": "evidence custodian",
                    },
                    {
                        "stage": "audit_replay_and_checkpoint",
                        "status": "complete",
                        "owner": "audit custodian",
                    },
                    {
                        "stage": "external_handoff",
                        "status": "required_not_executed",
                        "owner": "government accountable authority",
                    },
                ],
            },
            "workflow": {
                "implemented_operation": "offline_structural_transcript_replay",
                "production_state_changed": False,
                "external_actions_simulated": [
                    "authorization decision",
                    "atomic portfolio-registry commit",
                    "gateway activation",
                    "monitoring incident suspension",
                ],
                "rehearsed_states": [
                    "draft",
                    "registered",
                    "plan_frozen",
                    "evidence_frozen",
                    "assessed",
                    "optimized",
                    "commit_pending",
                    "authorized",
                    "active",
                    "suspended",
                ],
                "authority_boundary": (
                    "supplied mock state is replayed; no external action is performed"
                ),
                "boundary_notice": (
                    "workflow-rehearsal/00-DEMO-ONLY-NOT-AUTHORIZED.md"
                ),
            },
        },
        "role_guide": list(ROLE_GUIDE),
        "integrity": {
            "assessment_signature_verified": True,
            "optimization_signature_verified": True,
            "institutional_authority_verified": False,
            "demo_private_key_retained": False,
            "demo_public_key_path": public_key.relative_to(run_dir).as_posix(),
            "warning": (
                "temporary private key not retained after normal completion; the retained "
                "public key proves only this demo signature, not institutional authority"
            ),
            "artifacts": [
                {
                    "kind": "assessment_signed_manifest_v3",
                    "path": assessment_manifest_path.relative_to(run_dir).as_posix(),
                    "sha256": sha256_file(assessment_manifest_path),
                },
                {
                    "kind": "optimization_signed_manifest_v4",
                    "path": optimization_manifest_path.relative_to(run_dir).as_posix(),
                    "sha256": sha256_file(optimization_manifest_path),
                },
            ],
        },
        "audit": {
            "complete": audit_verification.complete,
            "event_count": audit_verification.event_count,
            "intent_count": audit_verification.intent_count,
            "completed_count": audit_verification.completed_count,
            "failed_count": audit_verification.failed_count,
            "orphaned_run_ids": [str(value) for value in audit_verification.orphaned_run_ids],
            "head_sha256": audit_verification.head_sha256,
            "checkpoint_path": audit_checkpoint_path.relative_to(run_dir).as_posix(),
            "checkpoint_sha256": sha256_file(audit_checkpoint_path),
        },
        "scenarios": [
            controlled_scenario,
            missing_scenario,
            leakage_scenario,
            tamper_scenario,
            mock_full,
            stale_registry,
            deployment_mismatch,
            monitoring_incident,
        ],
        "limitations": [
            "All model, evidence, policy, population, and healthcare descriptions are synthetic or fictional.",
            "The suite replays pre-bound evidence; it does not train a model or admit training-hook output into AssessmentRequest 5.0.",
            "The controlled example is a generic demonstration fixture, not healthcare validation.",
            "Structural protocol replay does not authenticate actors or perform external state changes.",
            "Protocol replay does not prove semantic completeness of external registry or gateway records.",
            "No result establishes general safety, clinical validity, fairness, legality, privacy, or production readiness.",
        ],
    }
    _validate_suite_report(report)
    report_path = run_dir / "suite-report.json"
    _write_json(report_path, report)
    guide_path = run_dir / "START-HERE.md"
    guide_path.write_text(_render_markdown(report), encoding="utf-8", newline="\n")
    return report


def _resolve_run_dir(output_root: Path, run_id: str) -> Path:
    if (
        not run_id
        or run_id in {".", ".."}
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
            for character in run_id
        )
    ):
        raise ValueError(
            "run-id may contain only letters, numbers, dash, underscore, and dot; "
            "it cannot be '.' or '..'"
        )
    resolved_root = output_root.resolve(strict=False)
    run_dir = (resolved_root / run_id).resolve(strict=False)
    if run_dir.parent != resolved_root:
        raise ValueError("run-id escapes the selected output root")
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fictional, offline government-health model-release demo suite"
        )
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="parent directory for a new timestamped run",
    )
    parser.add_argument(
        "--run-id",
        help="optional safe directory name; default is a UTC timestamp",
    )
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)
    run_id = args.run_id or started_at.strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir = _resolve_run_dir(args.output_root, run_id)
    report = run_demo_suite(run_dir, reference_time=started_at)

    print("MRA government-health guided demo")
    print("DEMO ONLY | FICTIONAL RECORDS | NO REAL PATIENT DATA | NOT AUTHORIZED")
    print()
    for index, scenario in enumerate(report["scenarios"], start=1):
        print(
            f"{index}/{len(report['scenarios'])} {scenario['scenario_id']}: "
            f"{scenario['result']}"
        )
    print()
    print(report["default_conclusion"])
    print(f"Open the plain-language report: {run_dir / 'START-HERE.md'}")
    print(f"Machine-readable report: {run_dir / 'suite-report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
