from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_release_assurance.empirical_workflow import (
    EmpiricalWorkflowConfig,
    run_empirical_xgboost_mlp_workflow,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run empirical XGBoost and MLP workflow")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "reproduction" / "model-audit-workflow" / "empirical-xgboost-mlp-config.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "model-audit-workflow" / "empirical-xgboost-mlp-report.json",
    )
    args = parser.parse_args()
    config = EmpiricalWorkflowConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    report = run_empirical_xgboost_mlp_workflow(config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "workflow_id": report["workflow_id"],
        "models": {
            item["kind"]: {
                "mean_accuracy": item["mean_accuracy"],
                "mean_roc_auc": item["mean_roc_auc"],
            }
            for item in report["models"]
        },
        "decision": report["decision"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
