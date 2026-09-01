#!/usr/bin/env python3
"""Run empirical membership-inference screens on public datasets.

This experiment produces attack floors/screens only. A weak or null attack never
establishes privacy and none of the outputs can authorize a model release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import scipy
import sklearn
import torch
import torch.nn as nn
import xgboost
from scipy.stats import beta
from sklearn.compose import ColumnTransformer
from sklearn.datasets import fetch_20newsgroups, fetch_openml
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from model_release_assurance.knowledge import KnowledgeIndex
from model_release_assurance.privacy_orchestration import PrivacyAuditPlan, build_privacy_audit_plan

PUBLIC_SOURCES = {
    "mnist": {
        "name": "MNIST",
        "openml_data_id": 554,
        "openml_version": 1,
        "url": "https://www.openml.org/d/554",
        "license": "CC BY-SA 3.0",
    },
    "adult": {
        "name": "Adult Census Income",
        "openml_data_id": 1590,
        "openml_version": 2,
        "url": "https://www.openml.org/d/1590",
        "license": "CC BY 4.0",
    },
    "20newsgroups": {
        "name": "20 Newsgroups",
        "url": "https://qwone.com/~jason/20Newsgroups/",
        "license": "dataset documentation does not declare a standardized license",
    },
}


def canonical_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(json.dumps(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def split_indices(size: int, counts: tuple[int, ...], seed: int) -> list[np.ndarray]:
    if sum(counts) > size:
        raise ValueError(f"requested {sum(counts)} rows from dataset with {size}")
    indices = np.random.default_rng(seed).permutation(size)[: sum(counts)]
    boundaries = np.cumsum((0, *counts))
    return [indices[boundaries[i] : boundaries[i + 1]] for i in range(len(counts))]


def attack_threshold(member_losses: np.ndarray, nonmember_losses: np.ndarray) -> float:
    values = np.unique(np.concatenate([member_losses, nonmember_losses]))
    best = (-1.0, float(values[0]))
    for threshold in values:
        tpr = float(np.mean(member_losses <= threshold))
        tnr = float(np.mean(nonmember_losses > threshold))
        candidate = ((tpr + tnr) / 2.0, float(threshold))
        if candidate[0] > best[0]:
            best = candidate
    return best[1]


def clopper_lower(successes: int, trials: int, confidence: float = 0.95) -> float:
    return 0.0 if successes == 0 else float(beta.ppf(1.0 - confidence, successes, trials - successes + 1))


def membership_result(
    calibration_member: np.ndarray,
    calibration_nonmember: np.ndarray,
    target_member: np.ndarray,
    target_nonmember: np.ndarray,
) -> dict[str, Any]:
    threshold = attack_threshold(calibration_member, calibration_nonmember)
    member_correct = target_member <= threshold
    nonmember_correct = target_nonmember > threshold
    successes = int(member_correct.sum() + nonmember_correct.sum())
    trials = int(member_correct.size + nonmember_correct.size)
    return {
        "attack": "disjoint_reference_calibrated_per_example_loss_threshold",
        "threshold": threshold,
        "member_trials": int(member_correct.size),
        "nonmember_trials": int(nonmember_correct.size),
        "true_members": int(member_correct.sum()),
        "true_nonmembers": int(nonmember_correct.sum()),
        "successes": successes,
        "trials": trials,
        "equal_prior_success": successes / trials,
        "one_sided_95pct_clopper_pearson_lower": clopper_lower(successes, trials),
        "advantage_over_random": successes / trials - 0.5,
        "evidence_class": "floor",
        "can_block": True,
        "can_clear": False,
        "raw_scores": {
            "target_member_losses": target_member.tolist(),
            "target_nonmember_losses": target_nonmember.tolist(),
            "calibration_member_losses": calibration_member.tolist(),
            "calibration_nonmember_losses": calibration_nonmember.tolist(),
        },
    }


class CNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv2d(1, 8, 3), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(8, 16, 3), nn.ReLU(), nn.AdaptiveAvgPool2d((3, 3)),
            nn.Flatten(), nn.Linear(16 * 3 * 3, 10),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.network(value)


class LSTMClassifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.lstm = nn.LSTM(28, 32, batch_first=True)
        self.output = nn.Linear(32, 10)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        sequence, _ = self.lstm(value)
        return self.output(sequence[:, -1])


class TextTransformer(nn.Module):
    def __init__(self, vocabulary: int, classes: int, length: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocabulary, 32, padding_idx=0)
        self.position = nn.Parameter(torch.zeros(1, length, 32))
        layer = nn.TransformerEncoderLayer(32, 4, 64, batch_first=True, dropout=0.0)
        self.encoder = nn.TransformerEncoder(layer, 1)
        self.output = nn.Linear(32, classes)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(self.embedding(value) + self.position[:, : value.shape[1]])
        mask = (value != 0).float().unsqueeze(-1)
        pooled = (encoded * mask).sum(1) / mask.sum(1).clamp_min(1.0)
        return self.output(pooled)


def torch_train(model: nn.Module, x: np.ndarray, y: np.ndarray, epochs: int, seed: int) -> nn.Module:
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    generator = torch.Generator().manual_seed(seed)
    dataset = torch.utils.data.TensorDataset(torch.from_numpy(x), torch.from_numpy(y).long())
    loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True, generator=generator)
    for _ in range(epochs):
        for features, labels in loader:
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(model(features), labels)
            loss.backward()
            optimizer.step()
    return model.eval()


def torch_losses(model: nn.Module, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        logits = model(torch.from_numpy(x))
        return nn.functional.cross_entropy(logits, torch.from_numpy(y).long(), reduction="none").numpy()


def torch_accuracy(model: nn.Module, x: np.ndarray, y: np.ndarray) -> float:
    with torch.no_grad():
        predictions = model(torch.from_numpy(x)).argmax(1).numpy()
    return float(np.mean(predictions == y))


def audit_torch_pair(
    name: str,
    constructor: Callable[[], nn.Module],
    x: np.ndarray,
    y: np.ndarray,
    indices: list[np.ndarray],
    epochs: int,
    seed: int,
) -> dict[str, Any]:
    target_train, target_nonmember, reference_train, reference_nonmember, utility = indices
    target = torch_train(constructor(), x[target_train], y[target_train], epochs, seed)
    reference = torch_train(constructor(), x[reference_train], y[reference_train], epochs, seed + 1)
    rng = np.random.default_rng(seed + 2)
    target_member = rng.choice(target_train, size=len(target_nonmember), replace=False)
    reference_member = rng.choice(reference_train, size=len(reference_nonmember), replace=False)
    attack = membership_result(
        torch_losses(reference, x[reference_member], y[reference_member]),
        torch_losses(reference, x[reference_nonmember], y[reference_nonmember]),
        torch_losses(target, x[target_member], y[target_member]),
        torch_losses(target, x[target_nonmember], y[target_nonmember]),
    )
    return {
        "model": name,
        "utility_accuracy": torch_accuracy(target, x[utility], y[utility]),
        "training_rows": len(target_train),
        "attack": attack,
    }


def load_mnist(cache: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    dataset = fetch_openml(data_id=554, as_frame=False, parser="auto", data_home=cache)
    x = np.asarray(dataset.data, dtype=np.float32).reshape(-1, 1, 28, 28) / 255.0
    y = np.asarray(dataset.target, dtype=np.int64)
    return x, y, {**PUBLIC_SOURCES["mnist"], "processed_snapshot_sha256": canonical_hash(x, y)}


def load_text(cache: Path, limit: int, seed: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    categories = ["comp.graphics", "rec.sport.baseball", "sci.space", "talk.politics.misc"]
    data = fetch_20newsgroups(
        subset="all", categories=categories, remove=("headers", "footers", "quotes"),
        data_home=cache, random_state=seed,
    )
    tokenized = [re.findall(r"[a-z]+", document.lower()) for document in data.data]
    counts: dict[str, int] = {}
    for document in tokenized:
        for token in document:
            counts[token] = counts.get(token, 0) + 1
    vocabulary = {token: index + 2 for index, (token, _) in enumerate(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:1998])}
    x = np.zeros((len(tokenized), limit), dtype=np.int64)
    for row, document in enumerate(tokenized):
        encoded = [vocabulary.get(token, 1) for token in document[:limit]]
        x[row, : len(encoded)] = encoded
    y = np.asarray(data.target, dtype=np.int64)
    return x, y, {**PUBLIC_SOURCES["20newsgroups"], "processed_snapshot_sha256": canonical_hash(x, y), "vocabulary_size": 2000}


def audit_xgboost(cache: Path, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = fetch_openml(data_id=1590, as_frame=True, parser="auto", data_home=cache)
    frame = dataset.data.copy()
    labels = LabelEncoder().fit_transform(dataset.target.astype(str)).astype(np.int64)
    indices = split_indices(len(frame), (1200, 400, 1200, 400, 500), seed)
    target_train, target_nonmember, reference_train, reference_nonmember, utility = indices
    numeric = list(frame.select_dtypes(include=["number"]).columns)
    categorical = [column for column in frame.columns if column not in numeric]
    preprocessor = ColumnTransformer([
        ("numeric", StandardScaler(), numeric),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=True), categorical),
    ])
    fit_rows = np.concatenate([target_train, reference_train])
    transformed = preprocessor.fit(frame.iloc[fit_rows]).transform(frame)

    def fit(rows: np.ndarray, random_state: int):
        model = xgboost.XGBClassifier(
            n_estimators=120, max_depth=6, learning_rate=0.08, subsample=1.0,
            colsample_bytree=1.0, n_jobs=1, random_state=random_state,
            eval_metric="logloss", tree_method="hist",
        )
        return model.fit(transformed[rows], labels[rows])

    target = fit(target_train, seed)
    reference = fit(reference_train, seed + 1)
    rng = np.random.default_rng(seed + 2)
    target_member = rng.choice(target_train, len(target_nonmember), replace=False)
    reference_member = rng.choice(reference_train, len(reference_nonmember), replace=False)

    def losses(model, rows):
        probabilities = np.clip(model.predict_proba(transformed[rows]), 1e-12, 1.0)
        return -np.log(probabilities[np.arange(len(rows)), labels[rows]])

    attack = membership_result(
        losses(reference, reference_member), losses(reference, reference_nonmember),
        losses(target, target_member), losses(target, target_nonmember),
    )
    report = {
        "model": "xgboost",
        "utility_accuracy": float(np.mean(target.predict(transformed[utility]) == labels[utility])),
        "training_rows": len(target_train),
        "attack": attack,
    }
    source = {**PUBLIC_SOURCES["adult"], "processed_snapshot_sha256": canonical_hash(labels, frame.astype(str).to_numpy(dtype="U"))}
    return report, source


def main() -> int:
    parser = argparse.ArgumentParser(description="Public-data privacy audit for CNN, LSTM, XGBoost, and compact Transformer")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "public-privacy-audit")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "reproduction" / "public-privacy" / "raw")
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    if args.plan is None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        plan = build_privacy_audit_plan(
            KnowledgeIndex.build(ROOT), seed=args.seed, epochs=args.epochs
        )
        args.plan = args.output_dir / "rag-audit-plan.json"
        args.plan.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
    else:
        plan = PrivacyAuditPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    if args.seed != plan.seed or args.epochs != plan.epochs:
        raise ValueError("worker seed and epochs must match the hash-bound RAG audit plan")
    if tuple(item.kind for item in plan.models) != ("cnn", "lstm", "xgboost", "llm"):
        raise ValueError("this worker requires the complete four-model audit plan")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    mnist_x, mnist_y, mnist_source = load_mnist(args.cache_dir)
    image_indices = split_indices(len(mnist_y), (1200, 400, 1200, 400, 500), args.seed)
    cnn = audit_torch_pair("cnn", CNN, mnist_x, mnist_y, image_indices, args.epochs, args.seed)
    sequence_x = mnist_x[:, 0]
    lstm = audit_torch_pair("lstm", LSTMClassifier, sequence_x, mnist_y, image_indices, args.epochs, args.seed + 10)
    xgb, adult_source = audit_xgboost(args.cache_dir, args.seed + 20)
    text_x, text_y, text_source = load_text(args.cache_dir, 96, args.seed)
    text_indices = split_indices(len(text_y), (1000, 350, 1000, 350, 400), args.seed + 30)
    transformer = audit_torch_pair(
        "compact_transformer_llm_proxy",
        lambda: TextTransformer(2000, 4, 96),
        text_x, text_y, text_indices, args.epochs, args.seed + 30,
    )
    report = {
        "schema_version": "1.0",
        "experiment_id": "public-data-four-model-membership-audit-v1",
        "orchestration": {
            "mode": "rag_planned_mcp_executable",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.plan_sha256,
            "plan_path": str(args.plan.resolve()),
            "guidance": {
                item.kind: list(item.guidance) for item in plan.models
            },
        },
        "experimental_only": True,
        "evidence_semantics": "empirical_attack_floors_and_screens_never_clear",
        "seed": args.seed,
        "epochs": args.epochs,
        "datasets": {"mnist": mnist_source, "adult": adult_source, "20newsgroups": text_source},
        "software": {
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "sklearn": sklearn.__version__, "torch": torch.__version__, "xgboost": xgboost.__version__,
        },
        "models": [cnn, lstm, xgb, transformer],
        "elapsed_seconds": time.time() - started,
        "decision": "no_release_authorization",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "privacy-audit-report.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {
        item["model"]: {
            "utility_accuracy": item["utility_accuracy"],
            "membership_success": item["attack"]["equal_prior_success"],
            "lower_95pct": item["attack"]["one_sided_95pct_clopper_pearson_lower"],
        }
        for item in report["models"]
    }
    print(json.dumps({"output": str(output), "results": summary, "decision": report["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
