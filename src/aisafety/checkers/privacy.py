"""Privacy Checker — membership inference attacks, differential privacy auditing."""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class PrivacyChecker(BaseChecker):
    name = "Privacy"
    category = "privacy"
    requires = ["art"]

    def check(
        self,
        model=None,
        train_data=None,
        train_labels=None,
        test_data=None,
        test_labels=None,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if model is None:
            return self._make_result([self._make_finding(
                "no_model", "No model provided",
                "Provide model and train/test data for privacy checks.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        if train_data is not None and test_data is not None:
            findings.append(self._membership_inference(
                model, train_data, train_labels, test_data, test_labels,
            ))

        findings.append(self._check_dp_training(model))
        findings.append(self._check_memorization(model, train_data, train_labels))

        return self._make_result(
            findings,
            metadata={"model_type": type(model).__name__},
        )

    def _membership_inference(self, model, train_data, train_labels, test_data, test_labels) -> Finding:
        """Run black-box membership inference attack."""
        try:
            from art.attacks.inference.membership_inference import MembershipInferenceBlackBox
            from art.estimators.classification import SklearnClassifier

            train_data = np.asarray(train_data, dtype=np.float32)
            test_data = np.asarray(test_data, dtype=np.float32)
            train_labels = np.asarray(train_labels)
            test_labels = np.asarray(test_labels)

            # One-hot encode labels if needed
            if train_labels.ndim == 1:
                n_classes = max(len(np.unique(train_labels)), 2)
                train_labels_oh = np.eye(n_classes)[train_labels.astype(int)]
                test_labels_oh = np.eye(n_classes)[test_labels.astype(int)]
            else:
                train_labels_oh = train_labels
                test_labels_oh = test_labels

            classifier = SklearnClassifier(model=model)

            attack = MembershipInferenceBlackBox(classifier, attack_model_type="rf")

            # Use subsets for efficiency
            n_train = min(500, len(train_data))
            n_test = min(500, len(test_data))

            attack.fit(
                train_data[:n_train], train_labels_oh[:n_train],
                test_data[:n_test], test_labels_oh[:n_test],
            )

            # Evaluate
            train_preds = attack.infer(train_data[:n_train], train_labels_oh[:n_train])
            test_preds = attack.infer(test_data[:n_test], test_labels_oh[:n_test])

            # Attack accuracy: should predict 1 for train, 0 for test
            train_acc = float(np.mean(train_preds))
            test_acc = float(1 - np.mean(test_preds))
            overall_acc = (train_acc + test_acc) / 2

            if overall_acc > 0.7:
                severity, status = Severity.HIGH, CheckStatus.FAIL
            elif overall_acc > 0.6:
                severity, status = Severity.MEDIUM, CheckStatus.WARN
            else:
                severity, status = Severity.INFO, CheckStatus.PASS

            return self._make_finding(
                "membership_inference", "Membership Inference Attack",
                f"Attack accuracy: {overall_acc:.4f} (random baseline: 0.5)",
                severity, status,
                details={
                    "attack_accuracy": overall_acc,
                    "train_member_detection": train_acc,
                    "test_nonmember_detection": test_acc,
                },
                recommendation="Model may be memorizing training data. Consider differential privacy or regularization."
                if status != CheckStatus.PASS else "",
            )

        except Exception as e:
            return self._make_finding(
                "membership_inference", "Membership Inference Attack",
                f"Failed: {e}", Severity.LOW, CheckStatus.ERROR,
            )

    def _check_dp_training(self, model) -> Finding:
        """Heuristic check for differential privacy training."""
        # Check for Opacus-wrapped models (PyTorch DP)
        model_class = type(model).__name__
        dp_indicators = ["GradSampleModule", "PrivacyEngine", "DPModel"]

        is_dp = any(indicator in model_class for indicator in dp_indicators)

        # Check for attributes that DP frameworks add
        if hasattr(model, "epsilon") or hasattr(model, "privacy_engine"):
            is_dp = True

        if is_dp:
            epsilon = getattr(model, "epsilon", "unknown")
            return self._make_finding(
                "dp_training", "Differential Privacy Training",
                f"Model appears to be trained with DP (ε={epsilon}).",
                Severity.INFO, CheckStatus.PASS,
                details={"dp_detected": True, "epsilon": str(epsilon)},
            )
        else:
            return self._make_finding(
                "dp_training", "Differential Privacy Training",
                "No differential privacy detected in model training.",
                Severity.MEDIUM, CheckStatus.WARN,
                details={"dp_detected": False},
                recommendation="Consider training with differential privacy (e.g., Opacus for PyTorch).",
            )

    def _check_memorization(self, model, train_data, train_labels) -> Finding:
        """Check for overfitting/memorization via training accuracy."""
        if train_data is None or train_labels is None:
            return self._make_finding(
                "memorization", "Memorization Check",
                "No training data provided.", Severity.LOW, CheckStatus.SKIPPED,
            )

        try:
            train_data = np.asarray(train_data)
            train_labels = np.asarray(train_labels)
            preds = model.predict(train_data[:1000])
            if preds.ndim > 1:
                preds = np.argmax(preds, axis=1)
            train_acc = float(np.mean(preds == train_labels[:1000]))

            if train_acc > 0.99:
                severity, status = Severity.HIGH, CheckStatus.WARN
                desc = f"Near-perfect training accuracy ({train_acc:.4f}) suggests memorization."
            else:
                severity, status = Severity.INFO, CheckStatus.PASS
                desc = f"Training accuracy: {train_acc:.4f}"

            return self._make_finding(
                "memorization", "Memorization Check",
                desc, severity, status,
                details={"training_accuracy": train_acc},
                recommendation="High training accuracy may indicate overfitting. Add regularization or use DP."
                if status != CheckStatus.PASS else "",
            )
        except Exception as e:
            return self._make_finding(
                "memorization", "Memorization Check",
                f"Failed: {e}", Severity.LOW, CheckStatus.ERROR,
            )
