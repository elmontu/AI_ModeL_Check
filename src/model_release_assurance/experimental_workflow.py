from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .integrity import sha256_file
from .knowledge import KnowledgeIndex
from .model_coverage import CoverageStatus, resolve_model_family


class ExperimentalModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(min_length=1)
    kind: Literal["cnn", "lstm", "xgboost", "llm"]
    model_family: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: str = Field(min_length=1)


class ExperimentalWorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    workflow_id: str = Field(min_length=1)
    experimental_only: Literal[True]
    models: tuple[ExperimentalModelSpec, ...] = Field(min_length=1)


_GUIDANCE_QUERIES = {
    "cnn": "vision CNN image membership inversion biometric linkage modality-specific worker",
    "lstm": "time series LSTM sequence trajectory linkage temporal reconstruction worker",
    "xgboost": "XGBoost tree linkage membership screening worker attack floor",
    "llm": "interactive LLM transcript watermark canary extraction cannot clear",
}


def _cnn_predict(model: dict[str, Any], inputs: list[list[float]]) -> int:
    kernel = model["kernel"]
    height, width = len(inputs), len(inputs[0])
    kh, kw = len(kernel), len(kernel[0])
    activation = 0.0
    for row in range(height - kh + 1):
        for column in range(width - kw + 1):
            value = sum(
                inputs[row + kr][column + kc] * kernel[kr][kc]
                for kr in range(kh)
                for kc in range(kw)
            ) + model["convolution_bias"]
            activation += max(0.0, value)
    return int(activation * model["output_weight"] + model["output_bias"] >= 0.0)


def _lstm_predict(model: dict[str, Any], inputs: list[float]) -> int:
    hidden = 0.0
    cell = 0.0
    for value in inputs:
        forget = 1.0 / (1.0 + math.exp(-(model["forget_x"] * value + model["forget_h"] * hidden)))
        incoming = 1.0 / (1.0 + math.exp(-(model["input_x"] * value + model["input_h"] * hidden)))
        candidate = math.tanh(model["cell_x"] * value + model["cell_h"] * hidden)
        output = 1.0 / (1.0 + math.exp(-(model["output_x"] * value + model["output_h"] * hidden)))
        cell = forget * cell + incoming * candidate
        hidden = output * math.tanh(cell)
    return int(hidden * model["classifier_weight"] + model["classifier_bias"] >= 0.0)


def _xgboost_predict(model: dict[str, Any], inputs: list[float]) -> int:
    score = model["base_score"]
    for stump in model["stumps"]:
        score += stump["left"] if inputs[stump["feature"]] < stump["threshold"] else stump["right"]
    return int(score >= 0.0)


def _llm_predict(model: dict[str, Any], prompt: str) -> str:
    token = prompt.lower().split()[-1]
    return model["next_token"].get(token, model["default_token"])


def evaluate_sample_artifact(kind: str, artifact: dict[str, Any]) -> dict[str, Any]:
    model = artifact["model"]
    cases = artifact["holdout_cases"]
    correct = 0
    observations = []
    for case in cases:
        if kind == "cnn":
            predicted = _cnn_predict(model, case["input"])
        elif kind == "lstm":
            predicted = _lstm_predict(model, case["input"])
        elif kind == "xgboost":
            predicted = _xgboost_predict(model, case["input"])
        elif kind == "llm":
            predicted = _llm_predict(model, case["prompt"])
        else:
            raise ValueError(f"unsupported experimental model kind: {kind}")
        expected = case["expected"]
        correct += predicted == expected
        observations.append({"case_id": case["case_id"], "predicted": predicted, "expected": expected})
    return {
        "metric": "exact_accuracy",
        "correct": correct,
        "cases": len(cases),
        "value": correct / len(cases),
        "observations": observations,
        "evidence_semantics": "synthetic_functional_screen_only",
        "can_clear": False,
    }


def run_experimental_workflow(
    manifest_path: Path,
    *,
    knowledge_index: KnowledgeIndex,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    spec = ExperimentalWorkflowSpec.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    results = []
    for item in spec.models:
        artifact_path = (root / item.artifact_path).resolve(strict=True)
        if not artifact_path.is_relative_to(root) or not artifact_path.is_file():
            raise ValueError(f"artifact escapes workflow directory: {item.artifact_path}")
        actual_hash = sha256_file(artifact_path)
        if actual_hash != item.artifact_sha256:
            raise ValueError(f"artifact hash mismatch for {item.experiment_id}")
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if artifact.get("kind") != item.kind:
            raise ValueError(f"artifact kind mismatch for {item.experiment_id}")
        coverage = resolve_model_family(item.model_family)
        retrieval = knowledge_index.search(_GUIDANCE_QUERIES[item.kind], limit=3)
        results.append(
            {
                "experiment_id": item.experiment_id,
                "kind": item.kind,
                "purpose": item.purpose,
                "artifact_path": artifact_path.relative_to(root).as_posix(),
                "artifact_sha256": actual_hash,
                "functional_evaluation": evaluate_sample_artifact(item.kind, artifact),
                "assurance_routing": coverage.as_dict(),
                "requires_dedicated_evidence": coverage.status is not CoverageStatus.GENERIC_CORE_APPLICABLE,
                "can_clear": False,
                "guidance": [
                    {
                        "source": hit.source,
                        "section": hit.section,
                        "source_sha256": hit.source_sha256,
                        "chunk_id": hit.chunk_id,
                        "score": hit.score,
                    }
                    for hit in retrieval
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "workflow_id": spec.workflow_id,
        "experimental_only": True,
        "decision": "no_release_authorization",
        "models": results,
    }
