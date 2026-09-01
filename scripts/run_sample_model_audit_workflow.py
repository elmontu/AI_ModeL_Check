from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_release_assurance.experimental_workflow import run_experimental_workflow
from model_release_assurance.knowledge import KnowledgeIndex


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the four-model experimental audit workflow")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reproduction" / "model-audit-workflow" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "model-audit-workflow" / "report.json",
    )
    args = parser.parse_args()
    report = run_experimental_workflow(
        args.manifest,
        knowledge_index=KnowledgeIndex.build(ROOT),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "workflow_id": report["workflow_id"],
        "models": len(report["models"]),
        "accuracies": {
            item["kind"]: item["functional_evaluation"]["value"] for item in report["models"]
        },
        "decision": report["decision"],
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
