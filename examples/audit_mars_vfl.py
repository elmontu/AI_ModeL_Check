#!/usr/bin/env python3
"""
Safety Audit: MARS-VFL (Vertical Federated Learning Benchmark)
https://github.com/shentt67/MARS-VFL

Runs against the REAL UCI-HAR dataset and REAL MARS-VFL model architecture.
No synthetic data — all results are from actual model training and evaluation.

Usage:
    python examples/audit_mars_vfl.py [--data_dir /path/to/MARS-VFL/data/]
"""

from __future__ import annotations

import argparse
import sys
import os
import time
import numpy as np

import torch
import torch.nn as nn

from aisafety.core.report import ReportBuilder
from aisafety.core.types import CheckStatus

# ============================================================
# 1. Load REAL UCI-HAR dataset
# ============================================================

def load_ucihar(data_dir: str):
    """Load the real UCI-HAR dataset from disk."""
    base = os.path.join(data_dir, "UCIHAR", "UCI HAR Dataset")

    train_x_path = os.path.join(base, "train", "X_train.txt")
    train_y_path = os.path.join(base, "train", "y_train.txt")
    test_x_path = os.path.join(base, "test", "X_test.txt")
    test_y_path = os.path.join(base, "test", "y_test.txt")

    for p in [train_x_path, train_y_path, test_x_path, test_y_path]:
        if not os.path.exists(p):
            print(f"ERROR: {p} not found.")
            print(f"Download UCI-HAR from: https://archive.ics.uci.edu/dataset/240/")
            print(f"Extract to: {base}")
            sys.exit(1)

    print("  Loading X_train.txt...")
    X_train = np.loadtxt(train_x_path).astype(np.float32)
    y_train = (np.loadtxt(train_y_path) - 1).astype(np.int64)  # labels 1-6 → 0-5

    print("  Loading X_test.txt...")
    X_test = np.loadtxt(test_x_path).astype(np.float32)
    y_test = (np.loadtxt(test_y_path) - 1).astype(np.int64)

    print(f"  Train: {X_train.shape} ({len(np.unique(y_train))} classes)")
    print(f"  Test:  {X_test.shape} ({len(np.unique(y_test))} classes)")
    return X_train, y_train, X_test, y_test


# ============================================================
# 2. REAL MARS-VFL UCIHAR model (copied from MARS-VFL source)
# ============================================================

class LocalModelForUCIHAR(nn.Module):
    """Exact copy of MARS-VFL's LocalModelForUCIHAR for client_num=2."""
    def __init__(self, input_dim: int):
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(input_dim, 140),
            nn.ReLU(),
            nn.Linear(140, 70),
            nn.ReLU(),
            nn.Linear(70, 16),
            nn.ReLU(),
        )

    def forward(self, x):
        return self.backbone(x)


class GlobalModelForUCIHAR(nn.Module):
    """Exact copy of MARS-VFL's GlobalModelForUCIHAR with concat aggregation."""
    def __init__(self, n_clients: int = 2, n_classes: int = 6):
        super().__init__()
        self.linear = nn.Linear(16 * n_clients, 16)
        self.classifier = nn.Linear(16, n_classes)

    def forward(self, input_list):
        x = torch.cat(input_list, dim=1)
        x = self.linear(x)
        x = self.classifier(x)
        return x


class VFLPipeline(nn.Module):
    """End-to-end wrapper for 2-client VFL (matches MARS-VFL's base method)."""
    def __init__(self):
        super().__init__()
        # UCIHAR: 561 features split into 348 + 213 (MARS-VFL default for 2 clients)
        self.local_0 = LocalModelForUCIHAR(348)
        self.local_1 = LocalModelForUCIHAR(213)
        self.global_model = GlobalModelForUCIHAR(n_clients=2, n_classes=6)

    def forward(self, x):
        x_0 = x[:, :348]
        x_1 = x[:, 348:]
        emb_0 = self.local_0(x_0)
        emb_1 = self.local_1(x_1)
        return self.global_model([emb_0, emb_1])

    def get_embeddings(self, x):
        """Return raw client embeddings (for privacy analysis)."""
        x_0 = x[:, :348]
        x_1 = x[:, 348:]
        with torch.no_grad():
            emb_0 = self.local_0(x_0)
            emb_1 = self.local_1(x_1)
        return emb_0.numpy(), emb_1.numpy()


class SklearnWrapper:
    """Wrap VFL pipeline as sklearn-compatible for aisafety checkers."""
    def __init__(self, model: nn.Module):
        self.model = model.eval()

    def predict(self, X):
        with torch.no_grad():
            logits = self.model(torch.tensor(X, dtype=torch.float32))
        return logits.numpy().argmax(axis=1)

    def predict_proba(self, X):
        with torch.no_grad():
            logits = self.model(torch.tensor(X, dtype=torch.float32))
            return torch.softmax(logits, dim=1).numpy()


# ============================================================
# 3. Train using MARS-VFL's base method
# ============================================================

def train_vfl(X_train, y_train, epochs=100, lr=0.01, batch_size=256):
    """Train VFL model using MARS-VFL's base training procedure."""
    model = VFLPipeline()
    criterion = nn.CrossEntropyLoss()

    # MARS-VFL uses separate optimizers per model component
    optimizer_global = torch.optim.SGD(model.global_model.parameters(), lr=lr, momentum=0.9)
    optimizer_local0 = torch.optim.SGD(model.local_0.parameters(), lr=lr, momentum=0.9)
    optimizer_local1 = torch.optim.SGD(model.local_1.parameters(), lr=lr, momentum=0.9)

    X_t = torch.tensor(X_train, dtype=torch.float32)
    y_t = torch.tensor(y_train, dtype=torch.long)

    model.train()
    for ep in range(epochs):
        perm = torch.randperm(len(X_t))
        total_loss = 0
        n_batches = 0

        for i in range(0, len(X_t), batch_size):
            idx = perm[i:i + batch_size]
            x_batch = X_t[idx]
            y_batch = y_t[idx]

            # VFL forward: split → local encode → global aggregate
            x_0 = x_batch[:, :348]
            x_1 = x_batch[:, 348:]

            emb_0 = model.local_0(x_0)
            emb_1 = model.local_1(x_1)

            # Detach for VFL simulation (each client computes independently)
            emb_0_detached = emb_0.detach().requires_grad_(True)
            emb_1_detached = emb_1.detach().requires_grad_(True)

            output = model.global_model([emb_0_detached, emb_1_detached])
            loss = criterion(output, y_batch)

            # Global backward
            optimizer_global.zero_grad()
            loss.backward()
            optimizer_global.step()

            # Propagate gradients back to local models (VFL gradient exchange)
            optimizer_local0.zero_grad()
            emb_0.backward(emb_0_detached.grad)
            optimizer_local0.step()

            optimizer_local1.zero_grad()
            emb_1.backward(emb_1_detached.grad)
            optimizer_local1.step()

            total_loss += loss.item()
            n_batches += 1

        if (ep + 1) % 20 == 0:
            avg_loss = total_loss / n_batches
            print(f"    Epoch {ep+1}/{epochs} — loss: {avg_loss:.4f}")

    model.eval()
    return model


# ============================================================
# 4. Run REAL safety audit
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default="/Users/elmohuang/MARS-VFL/data/",
                        help="Path to MARS-VFL data directory")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=0.01)
    args = parser.parse_args()

    print("=" * 70)
    print("MARS-VFL Safety Audit — REAL UCI-HAR Data")
    print("Architecture: 2-client VFL | MLP encoders | concat aggregation")
    print("Split: Client 0 = features[0:348], Client 1 = features[348:561]")
    print("=" * 70)

    builder = ReportBuilder(target_description="MARS-VFL UCIHAR (real data, 2-client VFL)")

    # --- Load REAL data ---
    print("\n[1/8] Loading REAL UCI-HAR dataset...")
    X_train, y_train, X_test, y_test = load_ucihar(args.data_dir)

    # --- Train REAL model ---
    print(f"\n[2/8] Training VFL model ({args.epochs} epochs, lr={args.lr})...")
    vfl_model = train_vfl(X_train, y_train, epochs=args.epochs, lr=args.lr)
    model = SklearnWrapper(vfl_model)

    # Real accuracy
    train_acc = float(np.mean(model.predict(X_train) == y_train))
    test_acc = float(np.mean(model.predict(X_test) == y_test))
    y_pred = model.predict(X_test)

    print(f"\n  === Real Model Performance ===")
    print(f"  Train accuracy: {train_acc:.4f}")
    print(f"  Test accuracy:  {test_acc:.4f}")

    # Per-class accuracy
    classes = ["Walking", "Stairs Up", "Stairs Down", "Sitting", "Standing", "Laying"]
    print(f"\n  Per-class test accuracy:")
    for c in range(6):
        mask = y_test == c
        if mask.sum() > 0:
            class_acc = float(np.mean(y_pred[mask] == y_test[mask]))
            print(f"    {classes[c]:12s}: {class_acc:.4f} ({mask.sum()} samples)")

    # --- FAIRNESS ---
    print("\n[3/8] Running Fairness checks...")
    from aisafety.checkers.tree.fairness import FairnessChecker
    fairness = FairnessChecker()
    if fairness.is_available():
        # Use real subject IDs as sensitive feature (simulates demographic groups)
        # UCI-HAR has 30 subjects — split into 2 groups for fairness analysis
        subject_test_path = os.path.join(args.data_dir, "UCIHAR", "UCI HAR Dataset", "test", "subject_test.txt")
        if os.path.exists(subject_test_path):
            subjects = np.loadtxt(subject_test_path).astype(int)
            # Group subjects: 1-15 = group A, 16-30 = group B
            sensitive = np.where(subjects <= 15, "subjects_1-15", "subjects_16-30")
            print(f"  Using real subject IDs as sensitive feature ({len(np.unique(subjects))} subjects)")
        else:
            # Fallback: use activity type as proxy
            sensitive = np.where(y_test < 3, "dynamic_activity", "static_activity")
            print(f"  Using activity type (dynamic vs static) as sensitive feature")

        result = fairness._timed_check(y_true=y_test, y_pred=y_pred, sensitive_features=sensitive)
        builder.add_result(result)
        for f in result.findings:
            print(f"  [{f.status.value:4s}] {f.title}: {f.description}")
    else:
        print("  Skipped (install fairlearn)")

    # --- DATA SAFETY ---
    print("\n[4/8] Running Data Safety checks...")
    from aisafety.checkers.tree.data_safety import DataSafetyChecker
    data_safety = DataSafetyChecker()
    if data_safety.is_available():
        import pandas as pd
        feature_names = [f"feat_{i}" for i in range(561)]
        df = pd.DataFrame(X_train, columns=feature_names)
        df["activity"] = y_train

        result = data_safety._timed_check(dataset=df, label_column="activity")
        builder.add_result(result)
        for f in result.findings:
            print(f"  [{f.status.value:4s}] {f.title}: {f.description}")
    else:
        print("  Skipped (install pandas, presidio)")

    # --- PRIVACY (real MIA, model extraction, memorization) ---
    print("\n[5/8] Running Privacy checks (real attacks)...")
    from aisafety.checkers.common.privacy import PrivacyChecker
    privacy = PrivacyChecker()
    if privacy.is_available():
        result = privacy._timed_check(
            model=model,
            train_data=X_train,
            train_labels=y_train,
            test_data=X_test,
            test_labels=y_test,
        )
        builder.add_result(result)
        for f in result.findings:
            print(f"  [{f.status.value:4s}] {f.title}: {f.description}")
    else:
        print("  Skipped (install adversarial-robustness-toolbox)")

    # --- VFL EMBEDDING ANALYSIS ---
    print("\n[6/8] Running VFL Embedding Privacy Analysis...")
    emb_0_train, emb_1_train = vfl_model.get_embeddings(torch.tensor(X_train[:500], dtype=torch.float32))
    emb_0_test, emb_1_test = vfl_model.get_embeddings(torch.tensor(X_test[:500], dtype=torch.float32))

    from aisafety.core.types import Finding, Severity
    from aisafety.core.types import CheckResult
    from datetime import datetime, timezone

    # Analyze embedding information leakage
    # Can we predict the label from a single client's embedding?
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score

    findings_emb = []

    for client_id, (emb_train, emb_test) in enumerate([
        (emb_0_train, emb_0_test),
        (emb_1_train, emb_1_test),
    ]):
        clf = RandomForestClassifier(n_estimators=50, random_state=42)
        clf.fit(emb_train, y_train[:500])
        label_acc_from_embedding = float(clf.score(emb_test, y_test[:500]))

        # Also check: can we reconstruct features from embeddings?
        from sklearn.linear_model import Ridge
        split_start = 0 if client_id == 0 else 348
        split_end = 348 if client_id == 0 else 561
        ridge = Ridge(alpha=1.0)
        ridge.fit(emb_train, X_train[:500, split_start:split_end])
        recon_score = float(ridge.score(emb_test, X_test[:500, split_start:split_end]))

        if label_acc_from_embedding > 0.7:
            sev, status = Severity.HIGH, CheckStatus.FAIL
        elif label_acc_from_embedding > 0.4:
            sev, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            sev, status = Severity.INFO, CheckStatus.PASS

        findings_emb.append(Finding(
            check_id=f"vfl.client_{client_id}_label_leakage",
            title=f"Client {client_id} Embedding → Label Inference",
            description=f"Label prediction from client {client_id}'s embedding: {label_acc_from_embedding:.4f} "
                        f"(random baseline: {1/6:.4f})",
            severity=sev, status=status,
            details={
                "label_accuracy_from_embedding": label_acc_from_embedding,
                "random_baseline": 1 / 6,
                "feature_reconstruction_r2": recon_score,
            },
            recommendation="Embedding leaks label information. Apply gradient perturbation or secure aggregation."
            if status != CheckStatus.PASS else "",
        ))

        if recon_score > 0.5:
            r_sev, r_status = Severity.CRITICAL, CheckStatus.FAIL
        elif recon_score > 0.2:
            r_sev, r_status = Severity.HIGH, CheckStatus.WARN
        else:
            r_sev, r_status = Severity.INFO, CheckStatus.PASS

        findings_emb.append(Finding(
            check_id=f"vfl.client_{client_id}_feature_reconstruction",
            title=f"Client {client_id} Embedding → Feature Reconstruction",
            description=f"Feature reconstruction R² from client {client_id}'s embedding: {recon_score:.4f}",
            severity=r_sev, status=r_status,
            details={"reconstruction_r2": recon_score, "n_features": split_end - split_start},
            recommendation="Features can be partially reconstructed from embeddings. "
                          "This is the GRNA attack vector documented in MARS-VFL."
            if r_status != CheckStatus.PASS else "",
        ))

        print(f"  Client {client_id}: label_acc={label_acc_from_embedding:.4f}, "
              f"feature_recon_R²={recon_score:.4f}")

    # Embedding similarity analysis
    cos_sim = np.mean([
        float(np.dot(emb_0_test[i], emb_1_test[i]) /
              (np.linalg.norm(emb_0_test[i]) * np.linalg.norm(emb_1_test[i]) + 1e-10))
        for i in range(len(emb_0_test))
    ])
    print(f"  Cross-client embedding cosine similarity: {cos_sim:.4f}")

    emb_result = CheckResult(
        checker_name="VFL Embedding Privacy",
        category="vfl_embedding_privacy",
        findings=findings_emb,
        metadata={
            "embedding_dim": 16,
            "n_clients": 2,
            "cross_client_cosine_similarity": cos_sim,
        },
    )
    builder.add_result(emb_result)

    # --- ALIGNMENT ---
    print("\n[7/8] Running Alignment checks (training dynamics)...")
    from aisafety.checkers.common.alignment import AlignmentChecker
    alignment = AlignmentChecker()

    # Use REAL training loss trajectory
    # Re-train briefly to capture trajectory data
    vfl_retrain = VFLPipeline()
    criterion = nn.CrossEntropyLoss()
    opt = torch.optim.SGD(vfl_retrain.parameters(), lr=0.01, momentum=0.9)
    X_t = torch.tensor(X_train, dtype=torch.float32)
    y_t = torch.tensor(y_train, dtype=torch.long)

    trajectories = []
    vfl_retrain.train()
    for ep in range(20):
        perm = torch.randperm(len(X_t))
        batch_losses = []
        batch_accs = []
        for i in range(0, min(len(X_t), 2560), 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            out = vfl_retrain(X_t[idx])
            loss = criterion(out, y_t[idx])
            loss.backward()
            opt.step()
            batch_losses.append(loss.item())
            acc = float((out.argmax(1) == y_t[idx]).float().mean())
            batch_accs.append(acc)

        trajectories.append({
            "states": [[float(np.mean(batch_losses))]],
            "actions": [int(np.argmax(np.bincount(y_train[:256])))],
            "rewards": [-float(np.mean(batch_losses))],  # negative loss as reward
        })

    gt_scores = [t["rewards"][0] for t in trajectories]

    result = alignment._timed_check(
        trajectories=trajectories,
        ground_truth_scores=gt_scores,
        reward_fn=lambda x: -sum(x),
    )
    builder.add_result(result)
    for f in result.findings:
        print(f"  [{f.status.value:4s}] {f.title}: {f.description}")

    # --- GOVERNANCE ---
    print("\n[8/8] Running Governance checks...")
    from aisafety.checkers.common.governance import GovernanceChecker
    governance = GovernanceChecker()

    report_so_far = builder.build()
    result = governance._timed_check(
        model_info={
            "name": "MARS-VFL UCIHAR",
            "version": "1.0 (shentt67/MARS-VFL)",
            "model_type": "Vertical Federated Learning — 2-client MLP",
            "description": f"2-client VFL for human activity recognition. "
                           f"Client 0: Linear(348→140→70→16), Client 1: Linear(213→140→70→16). "
                           f"Global: concat → Linear(32→16→6). "
                           f"Trained with SGD(lr={args.lr}, momentum=0.9) for {args.epochs} epochs.",
            "intended_use": "Research benchmark for VFL efficiency, robustness, and security evaluation.",
            "training_data": f"UCI HAR Dataset — {X_train.shape[0]} train / {X_test.shape[0]} test samples. "
                             f"561 accelerometer+gyroscope features from 30 subjects. "
                             f"6 classes: Walking, Stairs Up/Down, Sitting, Standing, Laying.",
            "limitations": f"Train acc: {train_acc:.4f}, Test acc: {test_acc:.4f}. "
                           "Vulnerable to gradient-based attacks (GRNA), label inference (PMC/AMC), "
                           "membership inference (MIA), and backdoor attacks (TECB/LFBA). "
                           "No differential privacy applied. Embeddings leak label information.",
            "ethical_considerations": "Activity recognition data reveals behavioral patterns. "
                                     "In VFL, a malicious client can infer labels or reconstruct "
                                     "other clients' features from shared gradients/embeddings.",
            "metrics": {
                "train_accuracy": train_acc,
                "test_accuracy": test_acc,
                "n_clients": 2,
                "aggregation": "concat",
                "embedding_dim": 16,
                "total_parameters": sum(p.numel() for p in vfl_model.parameters()),
            },
        },
        safety_report=report_so_far,
        framework="nist",
    )
    builder.add_result(result)
    for f in result.findings:
        print(f"  [{f.status.value:4s}] {f.title}: {f.description}")

    # ============================================================
    # Final Report
    # ============================================================
    report = builder.build()
    report_path = "mars_vfl_safety_report.json"
    builder.to_json(report_path)

    s = report.summary
    print("\n" + "=" * 70)
    print("MARS-VFL SAFETY AUDIT — REAL RESULTS")
    print("=" * 70)
    print(f"  Model:             MARS-VFL UCIHAR (2-client VFL)")
    print(f"  Dataset:           UCI-HAR ({X_train.shape[0]}+{X_test.shape[0]} samples, 561 features)")
    print(f"  Train accuracy:    {train_acc:.4f}")
    print(f"  Test accuracy:     {test_acc:.4f}")
    print(f"  Total parameters:  {sum(p.numel() for p in vfl_model.parameters()):,}")
    print(f"  ─────────────────────────────────────")
    print(f"  Total checks:      {s.total_checks}")
    print(f"  Passed:            {s.passed}")
    print(f"  Failed:            {s.failed}")
    print(f"  Warnings:          {s.warnings}")
    print(f"  Critical findings: {s.critical_findings}")
    print(f"  Overall status:    {s.overall_status.value.upper()}")
    print(f"\n  Report saved to: {report_path}")


if __name__ == "__main__":
    main()
