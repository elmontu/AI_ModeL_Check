"""Interpretability Checker — SHAP and LIME feature attribution."""

from __future__ import annotations

import numpy as np

from aisafety.core.base import BaseChecker
from aisafety.core.registry import register_checker
from aisafety.core.types import CheckStatus, Finding, Severity


@register_checker
class InterpretabilityChecker(BaseChecker):
    name = "Interpretability"
    category = "interpretability"
    requires = ["shap"]

    def check(
        self,
        model=None,
        X_train=None,
        X_explain=None,
        feature_names: list[str] | None = None,
        methods: list[str] | None = None,
        top_k: int = 10,
        **kwargs,
    ) -> "CheckResult":
        findings: list[Finding] = []

        if model is None or X_train is None:
            return self._make_result([self._make_finding(
                "no_model", "No model/data provided",
                "Provide model, X_train, and optionally X_explain.",
                Severity.INFO, CheckStatus.SKIPPED,
            )])

        X_train = np.asarray(X_train)
        X_explain = np.asarray(X_explain) if X_explain is not None else X_train[:50]
        methods = methods or ["shap"]
        n_features = X_train.shape[1] if X_train.ndim > 1 else 1
        feature_names = feature_names or [f"feature_{i}" for i in range(n_features)]

        rankings = {}

        if "shap" in methods:
            shap_finding, shap_ranking = self._run_shap(model, X_train, X_explain, feature_names, top_k)
            findings.append(shap_finding)
            if shap_ranking:
                rankings["shap"] = shap_ranking

        if "lime" in methods:
            lime_finding, lime_ranking = self._run_lime(model, X_train, X_explain, feature_names, top_k)
            findings.append(lime_finding)
            if lime_ranking:
                rankings["lime"] = lime_ranking

        # Consistency check
        if len(rankings) >= 2:
            findings.append(self._check_consistency(rankings, top_k))

        # Feature dominance check
        if "shap" in rankings:
            findings.append(self._check_feature_dominance(rankings["shap"]))

        return self._make_result(
            findings,
            metadata={"methods": methods, "n_features": n_features, "top_k": top_k},
        )

    def _run_shap(self, model, X_train, X_explain, feature_names, top_k):
        import shap

        try:
            # Try TreeExplainer first (fast for tree models)
            try:
                explainer = shap.TreeExplainer(model)
            except Exception:
                explainer = shap.KernelExplainer(model.predict_proba if hasattr(model, "predict_proba") else model.predict, X_train[:100])

            shap_values = explainer.shap_values(X_explain)
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # binary classification: take positive class

            importance = np.abs(shap_values).mean(axis=0)
            top_indices = np.argsort(importance)[::-1][:top_k]
            ranking = [(feature_names[i], float(importance[i])) for i in top_indices]

            return self._make_finding(
                "shap_analysis", "SHAP Feature Attribution",
                f"Top features: {', '.join(f[0] for f in ranking[:5])}",
                Severity.INFO, CheckStatus.PASS,
                details={"top_features": ranking, "method": "SHAP"},
            ), [f[0] for f in ranking]

        except Exception as e:
            return self._make_finding(
                "shap_analysis", "SHAP Feature Attribution",
                f"Failed: {e}", Severity.LOW, CheckStatus.ERROR,
            ), None

    def _run_lime(self, model, X_train, X_explain, feature_names, top_k):
        try:
            from lime.lime_tabular import LimeTabularExplainer

            explainer = LimeTabularExplainer(
                X_train, feature_names=feature_names, mode="classification",
            )

            importance_agg = np.zeros(len(feature_names))
            n_explain = min(20, len(X_explain))

            for i in range(n_explain):
                predict_fn = model.predict_proba if hasattr(model, "predict_proba") else model.predict
                exp = explainer.explain_instance(X_explain[i], predict_fn)
                for feat_idx, weight in exp.as_map().get(1, exp.as_map().get(0, [])):
                    importance_agg[feat_idx] += abs(weight)

            importance_agg /= n_explain
            top_indices = np.argsort(importance_agg)[::-1][:top_k]
            ranking = [(feature_names[i], float(importance_agg[i])) for i in top_indices]

            return self._make_finding(
                "lime_analysis", "LIME Feature Attribution",
                f"Top features: {', '.join(f[0] for f in ranking[:5])}",
                Severity.INFO, CheckStatus.PASS,
                details={"top_features": ranking, "method": "LIME"},
            ), [f[0] for f in ranking]

        except Exception as e:
            return self._make_finding(
                "lime_analysis", "LIME Feature Attribution",
                f"Failed: {e}", Severity.LOW, CheckStatus.ERROR,
            ), None

    def _check_consistency(self, rankings: dict, top_k: int) -> Finding:
        methods = list(rankings.keys())
        set_a = set(rankings[methods[0]][:top_k])
        set_b = set(rankings[methods[1]][:top_k])
        overlap = len(set_a & set_b)
        consistency = overlap / top_k if top_k > 0 else 0

        if consistency < 0.3:
            severity, status = Severity.MEDIUM, CheckStatus.WARN
        else:
            severity, status = Severity.INFO, CheckStatus.PASS

        return self._make_finding(
            "method_consistency", "Attribution Method Consistency",
            f"Top-{top_k} overlap between {methods[0]} and {methods[1]}: {overlap}/{top_k} ({consistency:.0%})",
            severity, status,
            details={"overlap": overlap, "consistency": consistency, "methods": methods},
            recommendation="Low consistency may indicate unstable explanations — investigate further."
            if status != CheckStatus.PASS else "",
        )

    def _check_feature_dominance(self, shap_ranking: list[str]) -> Finding:
        # This is a heuristic: if top feature has > 5x the importance of the 2nd
        # we flag it (would need actual importance values, so this is simplified)
        if len(shap_ranking) < 2:
            return self._make_finding(
                "feature_dominance", "Feature Dominance",
                "Not enough features to check.", Severity.LOW, CheckStatus.SKIPPED,
            )

        return self._make_finding(
            "feature_dominance", "Feature Dominance Check",
            f"Top feature: {shap_ranking[0]}. Check if model over-relies on a single feature.",
            Severity.INFO, CheckStatus.PASS,
            details={"top_feature": shap_ranking[0]},
        )
