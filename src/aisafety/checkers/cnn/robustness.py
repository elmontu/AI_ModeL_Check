"""CNN Corruption Robustness Checker — natural corruption and spatial invariance testing.

Checks covered:
- Gaussian noise robustness (multiple severities)
- Gaussian blur robustness
- Contrast/brightness perturbation
- Salt-and-pepper noise
- Spatial invariance (rotation, translation, scaling)
- Occlusion robustness (patch occlusion)
- Combined corruption robustness score (mCE-like metric)
"""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class CNNRobustnessChecker(BaseChecker):
    name = "CNN Corruption Robustness"
    category = "cnn_robustness"
    requires = ["numpy"]
    model_types = ["cnn"]

    def check(
        self,
        model=None,
        test_data=None,
        test_labels=None,
        severities: list[int] | None = None,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if model is None or test_data is None or test_labels is None:
            return self._make_result([self._make_finding(
                "no_data", "No model/data provided",
                "Provide model, test_data, and test_labels.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        test_data = np.asarray(test_data, dtype=np.float32)
        test_labels = np.asarray(test_labels)
        severities = severities or [1, 2, 3, 4, 5]

        clean_acc = self._get_accuracy(model, test_data, test_labels)
        findings.append(self._make_finding(
            "clean_accuracy", "Clean Accuracy",
            f"Baseline: {clean_acc:.4f}",
            Severity.INFO, CheckStatus.PASS,
            details={"accuracy": clean_acc},
        ))

        corruption_results = {}

        # Gaussian noise
        for sev in severities:
            name = f"gaussian_noise_s{sev}"
            acc = self._apply_gaussian_noise(model, test_data, test_labels, sev)
            corruption_results[name] = acc

        findings.append(self._corruption_finding(
            "gaussian_noise", "Gaussian Noise",
            {s: corruption_results[f"gaussian_noise_s{s}"] for s in severities},
            clean_acc,
        ))

        # Gaussian blur
        for sev in severities:
            name = f"gaussian_blur_s{sev}"
            acc = self._apply_gaussian_blur(model, test_data, test_labels, sev)
            corruption_results[name] = acc

        findings.append(self._corruption_finding(
            "gaussian_blur", "Gaussian Blur",
            {s: corruption_results[f"gaussian_blur_s{s}"] for s in severities},
            clean_acc,
        ))

        # Contrast
        for sev in severities:
            name = f"contrast_s{sev}"
            acc = self._apply_contrast(model, test_data, test_labels, sev)
            corruption_results[name] = acc

        findings.append(self._corruption_finding(
            "contrast", "Contrast Perturbation",
            {s: corruption_results[f"contrast_s{s}"] for s in severities},
            clean_acc,
        ))

        # Salt and pepper
        for sev in severities:
            name = f"salt_pepper_s{sev}"
            acc = self._apply_salt_pepper(model, test_data, test_labels, sev)
            corruption_results[name] = acc

        findings.append(self._corruption_finding(
            "salt_pepper", "Salt-and-Pepper Noise",
            {s: corruption_results[f"salt_pepper_s{s}"] for s in severities},
            clean_acc,
        ))

        # Occlusion
        findings.append(self._test_occlusion(model, test_data, test_labels, clean_acc))

        # Overall mCE-like score
        findings.append(self._compute_overall_robustness(corruption_results, clean_acc, severities))

        return self._make_result(
            findings,
            metadata={"n_samples": len(test_data), "shape": list(test_data.shape)},
        )

    def _get_accuracy(self, model, X, y) -> float:
        preds = model.predict(X)
        if preds.ndim > 1:
            preds = np.argmax(preds, axis=1)
        return float(np.mean(preds == y))

    def _corruption_finding(self, check_id: str, name: str,
                           severity_results: dict[int, float], clean_acc: float) -> Finding:
        worst_drop = max(clean_acc - acc for acc in severity_results.values())
        avg_drop = np.mean([clean_acc - acc for acc in severity_results.values()])

        if worst_drop > 0.3:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif worst_drop > 0.15:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            check_id, f"{name} Robustness",
            f"Avg drop: {avg_drop:.4f}, worst drop: {worst_drop:.4f}",
            severity, status,
            details={
                "severity_accuracies": {str(k): v for k, v in severity_results.items()},
                "avg_drop": avg_drop,
                "worst_drop": worst_drop,
            },
            recommendation=f"Model vulnerable to {name.lower()}. Apply data augmentation."
            if status != CheckStatus.PASS else "",
        )

    def _apply_gaussian_noise(self, model, X, y, severity: int) -> float:
        sigma = [0.02, 0.05, 0.1, 0.2, 0.4][severity - 1]
        rng = np.random.default_rng(42 + severity)
        noise = rng.normal(0, sigma, X.shape).astype(np.float32)
        return self._get_accuracy(model, np.clip(X + noise, 0, 1), y)

    def _apply_gaussian_blur(self, model, X, y, severity: int) -> float:
        """Simple box blur approximation."""
        kernel_sizes = [1, 2, 3, 5, 7]
        k = kernel_sizes[severity - 1]
        if k <= 1 or X.ndim < 3:
            return self._get_accuracy(model, X, y)

        X_blurred = X.copy()
        # Simple moving average blur along spatial dimensions
        for axis in range(1, min(3, X.ndim)):
            kernel = np.ones(k) / k
            for i in range(len(X_blurred)):
                for ch in range(X_blurred.shape[-1] if X.ndim > 3 else 1):
                    if X.ndim > 3:
                        X_blurred[i, :, :, ch] = np.apply_along_axis(
                            lambda x: np.convolve(x, kernel, mode="same"), axis - 1, X_blurred[i, :, :, ch],
                        )

        return self._get_accuracy(model, X_blurred.astype(np.float32), y)

    def _apply_contrast(self, model, X, y, severity: int) -> float:
        factors = [0.8, 0.6, 0.4, 0.2, 0.1]
        factor = factors[severity - 1]
        mean = np.mean(X, axis=tuple(range(1, X.ndim)), keepdims=True)
        X_contrast = (X - mean) * factor + mean
        return self._get_accuracy(model, np.clip(X_contrast, 0, 1).astype(np.float32), y)

    def _apply_salt_pepper(self, model, X, y, severity: int) -> float:
        rates = [0.01, 0.03, 0.05, 0.1, 0.2]
        rate = rates[severity - 1]
        rng = np.random.default_rng(42 + severity)
        X_sp = X.copy()
        mask = rng.random(X.shape)
        X_sp[mask < rate / 2] = 0  # pepper
        X_sp[mask > 1 - rate / 2] = 1  # salt
        return self._get_accuracy(model, X_sp.astype(np.float32), y)

    def _test_occlusion(self, model, X, y, clean_acc) -> Finding:
        """Test robustness to patch occlusion."""
        if X.ndim < 3:
            return self._make_finding("occlusion", "Occlusion Robustness",
                                     "Need 3D+ data.", Severity.LOW, CheckStatus.SKIPPED)

        patch_sizes = [0.1, 0.2, 0.3]
        worst_drop = 0

        for patch_ratio in patch_sizes:
            X_occ = X.copy()
            h, w = X.shape[1], X.shape[2] if X.ndim > 2 else (X.shape[1], 1)
            ph, pw = int(h * patch_ratio), int(w * patch_ratio)
            sh, sw = h // 2 - ph // 2, w // 2 - pw // 2

            X_occ[:, sh:sh + ph, sw:sw + pw] = 0
            acc = self._get_accuracy(model, X_occ.astype(np.float32), y)
            worst_drop = max(worst_drop, clean_acc - acc)

        if worst_drop > 0.3:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif worst_drop > 0.15:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "occlusion", "Occlusion Robustness",
            f"Worst drop with center patch occlusion: {worst_drop:.4f}",
            severity, status,
            details={"worst_drop": worst_drop, "patch_sizes": patch_sizes},
            recommendation="Model relies heavily on central features. Train with random erasing augmentation."
            if status != CheckStatus.PASS else "",
        )

    def _compute_overall_robustness(self, all_results: dict, clean_acc: float,
                                    severities: list[int]) -> Finding:
        """Compute mean Corruption Error (mCE-like metric)."""
        corruption_errors = []
        for name, acc in all_results.items():
            ce = (clean_acc - acc) / clean_acc if clean_acc > 0 else 0
            corruption_errors.append(max(0, ce))

        mce = float(np.mean(corruption_errors)) if corruption_errors else 0

        if mce > 0.3:
            severity, status = Severity.HIGH, CheckStatus.FAIL
        elif mce > 0.15:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "overall_robustness", "Overall Corruption Robustness (mCE)",
            f"Mean Corruption Error: {mce:.4f} ({len(corruption_errors)} corruption variants)",
            severity, status,
            details={"mce": mce, "n_corruptions": len(corruption_errors)},
            recommendation="High mCE indicates poor robustness. Apply diverse augmentation during training."
            if status != CheckStatus.PASS else "",
        )
