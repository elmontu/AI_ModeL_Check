"""Shared input contracts for HTTP requests, persisted jobs and worker retries."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(default="Public data training", min_length=1, max_length=100)
    dataset: Literal["sklearn-breast-cancer", "sklearn-wine", "sklearn-digits", "sklearn-diabetes"] = "sklearn-breast-cancer"
    preset: Literal["xgboost-small", "logistic", "random-forest", "mlp", "mlp-finetuned", "cnn", "svm", "ensemble", "ridge", "forest-regression"] = "xgboost-small"

    @model_validator(mode="after")
    def validate_pair(self):
        if (self.preset in {"ridge", "forest-regression"}) != (self.dataset == "sklearn-diabetes"):
            raise ValueError("regression presets require the diabetes dataset")
        if self.preset == "cnn" and self.dataset != "sklearn-digits":
            raise ValueError("CNN preset requires digits")
        if self.preset == "xgboost-small" and self.dataset != "sklearn-breast-cancer":
            raise ValueError("registered XGBoost demo requires the breast-cancer dataset")
        return self


class LanguageOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    model: str = Field(min_length=1, max_length=150)
