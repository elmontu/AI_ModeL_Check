from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_release_assurance.knowledge import KnowledgeIndex


ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("What creates a model release authorization?", {"docs/model-release-assurance-protocol.md"}),
    ("How are lower-bound attack results used?", {"docs/architecture.md", "docs/mathematical-foundations.md"}),
    ("What is the trusted computing base of the Lean proof?", {"docs/formal-verification.md"}),
    ("Which controls apply to interactive LLM watermark and canary tests?", {"docs/llm-watermark-canary.md", "docs/protocol-case-studies.md"}),
    ("What model families and modalities are covered?", {"docs/model-family-coverage.md"}),
    ("What fields are required in assessment request schema version 3?", {"schemas/assessment-request-v3.json"}),
    ("How is the production registry and gateway expected to work?", {"docs/reference/production-roadmap.md", "docs/model-release-assurance-protocol.md", "docs/architecture.md"}),
    ("What governance obligations cover contestation and affected parties?", {"docs/governance-core.md", "docs/model-release-assurance-protocol.md"}),
)


def evaluate(index: KnowledgeIndex, top_k: int = 5) -> dict[str, object]:
    reciprocal_ranks: list[float] = []
    hits = 0
    details = []
    for query, relevant_sources in CASES:
        results = index.search(query, limit=top_k)
        rank = next((position for position, hit in enumerate(results, 1) if hit.source in relevant_sources), None)
        hits += rank is not None
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
        details.append(
            {
                "query": query,
                "relevant_sources": sorted(relevant_sources),
                "rank": rank,
                "returned_sources": [hit.source for hit in results],
            }
        )
    return {
        "cases": len(CASES),
        "top_k": top_k,
        "hit_rate_at_k": hits / len(CASES),
        "mean_reciprocal_rank": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic MRA knowledge retrieval")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(KnowledgeIndex.build(args.repository_root), args.top_k)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["hit_rate_at_k"] >= 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(main())
