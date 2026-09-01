from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .integrity import canonical_json_bytes, sha256_bytes
from .knowledge import KnowledgeIndex
from .model_coverage import resolve_model_family


class PrivacyAuditPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["cnn", "lstm", "xgboost", "llm"]
    model_family: str
    public_dataset: Literal["mnist", "adult", "20newsgroups"]
    attacks: tuple[Literal["membership_loss_threshold"], ...]
    evidence_semantics: Literal["floor_or_screen_never_clear"]
    limitations: tuple[str, ...]
    guidance: tuple[dict[str, Any], ...]


class PrivacyAuditPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    plan_id: str = Field(min_length=1)
    seed: int
    epochs: int = Field(ge=1, le=20)
    experimental_only: Literal[True]
    models: tuple[PrivacyAuditPlanItem, ...]
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_hash(self) -> "PrivacyAuditPlan":
        material = self.model_dump(mode="json", exclude={"plan_sha256"})
        if sha256_bytes(canonical_json_bytes(material)) != self.plan_sha256:
            raise ValueError("privacy audit plan hash mismatch")
        return self


_SETTINGS = {
    "cnn": {
        "family": "cnn",
        "dataset": "mnist",
        "query": "CNN vision membership inference inversion public dataset privacy attack evidence",
        "limitations": ("no image reconstruction or model inversion attack", "bounded MNIST sample"),
    },
    "lstm": {
        "family": "time_series",
        "dataset": "mnist",
        "query": "LSTM sequence membership trajectory reconstruction privacy audit evidence",
        "limitations": ("MNIST rows are used as synthetic sequences", "no temporal reconstruction attack"),
    },
    "xgboost": {
        "family": "xgboost",
        "dataset": "adult",
        "query": "XGBoost membership attack floor calibrated loss public data audit",
        "limitations": ("single loss-threshold attack", "public preprocessing is outside a private mechanism"),
    },
    "llm": {
        "family": "llm",
        "dataset": "20newsgroups",
        "query": "interactive LLM membership canary extraction transcript RAG tools memory privacy audit",
        "limitations": ("compact Transformer classifier proxy, not a generative LLM", "no canary extraction or adaptive transcript attack"),
    },
}


def build_privacy_audit_plan(
    index: KnowledgeIndex,
    *,
    seed: int = 20260830,
    epochs: int = 3,
    kinds: tuple[str, ...] = ("cnn", "lstm", "xgboost", "llm"),
) -> PrivacyAuditPlan:
    if len(kinds) != len(set(kinds)) or any(kind not in _SETTINGS for kind in kinds):
        raise ValueError("model kinds must be unique members of cnn, lstm, xgboost, llm")
    items = []
    for kind in kinds:
        setting = _SETTINGS[kind]
        family = resolve_model_family(setting["family"])
        hits = index.search(setting["query"], limit=4)
        items.append(
            PrivacyAuditPlanItem(
                kind=kind,
                model_family=family.family_id,
                public_dataset=setting["dataset"],
                attacks=("membership_loss_threshold",),
                evidence_semantics="floor_or_screen_never_clear",
                limitations=setting["limitations"],
                guidance=tuple(
                    {
                        "source": hit.source,
                        "section": hit.section,
                        "source_sha256": hit.source_sha256,
                        "chunk_id": hit.chunk_id,
                        "score": hit.score,
                    }
                    for hit in hits
                ),
            )
        )
    material = {
        "schema_version": "1.0",
        "plan_id": "rag-guided-public-privacy-audit-v1",
        "seed": seed,
        "epochs": epochs,
        "experimental_only": True,
        "models": [item.model_dump(mode="json") for item in items],
    }
    return PrivacyAuditPlan(**material, plan_sha256=sha256_bytes(canonical_json_bytes(material)))
