"""YAML configuration loader for checker parameters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class CheckerConfig(BaseModel):
    """Configuration for a single checker."""

    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)


class AuditConfig(BaseModel):
    """Top-level audit configuration."""

    target: dict[str, str] = Field(default_factory=dict)
    checkers: dict[str, CheckerConfig] = Field(default_factory=dict)
    output: dict[str, str] = Field(default_factory=lambda: {"format": "json", "path": "safety_report.json"})


def load_config(path: str | Path) -> AuditConfig:
    """Load audit configuration from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text())
    if raw is None:
        return AuditConfig()

    checkers = {}
    for name, cfg in raw.get("checkers", {}).items():
        if isinstance(cfg, dict):
            enabled = cfg.pop("enabled", True)
            checkers[name] = CheckerConfig(enabled=enabled, params=cfg)
        else:
            checkers[name] = CheckerConfig(enabled=bool(cfg))

    return AuditConfig(
        target=raw.get("target", {}),
        checkers=checkers,
        output=raw.get("output", {"format": "json", "path": "safety_report.json"}),
    )


DEFAULT_CONFIG_TEMPLATE = """\
# AI Safety Checker configuration
target:
  description: "My AI Model"
  type: "sklearn"  # sklearn | pytorch | llm_endpoint

checkers:
  data_safety:
    enabled: true
    # dataset: "data/train.csv"
    # text_columns: ["description"]
    # sensitive_columns: ["gender", "race"]
    # label_column: "approved"

  adversarial:
    enabled: false
    # attacks: ["fgsm", "pgd"]
    # eps: 0.3

  fairness:
    enabled: true
    # threshold: 0.8

  interpretability:
    enabled: true
    # methods: ["shap", "lime"]

  privacy:
    enabled: false

  alignment:
    enabled: false

  llm_prompt_safety:
    enabled: false
    # endpoint_url: "https://api.example.com/v1/chat"
    # api_key_env: "LLM_API_KEY"

  llm_content_safety:
    enabled: false

  llm_guardrails:
    enabled: false

  agentic_safety:
    enabled: false

  governance:
    enabled: true

output:
  format: "json"
  path: "safety_report.json"
"""
