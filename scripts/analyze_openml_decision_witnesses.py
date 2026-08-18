#!/usr/bin/env python3
"""Independently replay selected OpenML decision-theory witnesses from raw rows."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_guess(rows: list[dict[str, Any]], field: str) -> float:
    return len({row[field] for row in rows}) / len(rows)


def attribute_value(rows: list[dict[str, Any]], field: str) -> float:
    cells: dict[str, Counter[int]] = defaultdict(Counter)
    for row in rows:
        cells[row[field]][int(row["target_attribute"])] += 1
    return sum(max(counts.values()) for counts in cells.values()) / len(rows)


def assert_close(actual: float, expected: float, label: str, errors: list[str]) -> None:
    if abs(actual - expected) > 1e-12:
        errors.append(f"{label}: replay {actual} != reported {expected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    if sha256_file(args.raw) != summary["raw_witness"]["sha256"]:
        raise ValueError("raw witness hash mismatch")
    with gzip.open(args.raw, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    errors: list[str] = []

    metric = raw["metric_reversal"]
    metric_witness = metric["witness"]
    metric_rows = metric["rows"]
    identity = (exact_guess(metric_rows, "left_observation"), exact_guess(metric_rows, "right_observation"))
    attribute = (attribute_value(metric_rows, "left_observation"), attribute_value(metric_rows, "right_observation"))
    for actual, expected, label in zip(identity + attribute, metric_witness["identity_values"] + metric_witness["attribute_values"], ("identity left", "identity right", "attribute left", "attribute right"), strict=True):
        assert_close(actual, expected, label, errors)
    if (identity[0] - identity[1]) * (attribute[0] - attribute[1]) >= 0.0:
        errors.append("decision-metric ranking did not reverse")

    anchor = raw["anchoring_reversal"]
    anchor_witness = anchor["witness"]
    anchor_rows = anchor["rows"]
    left_anchor = [row for row in anchor_rows if row["anchor"] == "left_favouring"]
    right_anchor = [row for row in anchor_rows if row["anchor"] == "right_favouring"]
    left_values = (exact_guess(left_anchor, "left_observation"), exact_guess(left_anchor, "right_observation"))
    right_values = (exact_guess(right_anchor, "left_observation"), exact_guess(right_anchor, "right_observation"))
    for actual, expected, label in zip(left_values + right_values, anchor_witness["left_anchor_values"] + anchor_witness["right_anchor_values"], ("left anchor/left", "left anchor/right", "right anchor/left", "right anchor/right"), strict=True):
        assert_close(actual, expected, label, errors)
    if left_values[0] <= left_values[1] or right_values[1] <= right_values[0]:
        errors.append("population-anchor ranking did not reverse")

    substitution = raw["substitution_separation"]
    substitution_witness = substitution["witness"]
    substitution_rows = substitution["rows"]
    label_value = exact_guess(substitution_rows, "evaluated_label_observation")
    leaf_value = exact_guess(substitution_rows, "left_observation")
    assert_close(label_value, substitution_witness["evaluated_exact_identity_value"], "substitution evaluated", errors)
    assert_close(leaf_value, substitution_witness["released_exact_identity_value"], "substitution released", errors)
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in substitution_rows:
        mapping[row["left_observation"]].add(row["evaluated_label_observation"])
    if any(len(labels) != 1 for labels in mapping.values()):
        errors.append("label surface is not a deterministic garbling of leaf signatures")
    if leaf_value <= label_value:
        errors.append("released surface did not strictly separate from evaluated surface")

    result = {
        "validation": {
            "raw_hash_and_all_values_replayed": not errors,
            "errors": errors,
        },
        "decision_metric_reversal": metric_witness,
        "population_anchor_reversal": anchor_witness,
        "substitution_separation": substitution_witness,
        "interpretation": [
            "The metric reversal is an empirical witness of Blackwell incomparability, not proof that no total-order extension exists.",
            "It proves that no gain-independent scalar ordering can agree with both witnessed decision problems.",
            "The anchoring witness keeps exact identity guessing fixed and changes only the declared finite-population prior.",
            "The substitution witness proves that a label-only assessment cannot certify a full leaf-signature release for all decision problems.",
        ],
        "claim_boundary": summary["claim_boundary"],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    m, a, s = metric_witness, anchor_witness, substitution_witness
    args.output_md.write_text("\n".join([
        "# OpenML decision-theory witnesses",
        "",
        "## Scope",
        "",
        f"The search replayed all {summary['search']['datasets_considered']} retained OpenML composition populations and examined {summary['search']['common_roster_rows_examined']:,} common-roster records. These are record-level benchmark witnesses, not METABRIC or government-population estimates.",
        "",
        "## Decision-metric reversal",
        "",
        f"On {m['dataset_name']} (OpenML {m['dataset_id']}, n={m['records']:,}), releases {m['left_seed']} and {m['right_seed']} reverse order between exact identity guessing ({m['identity_values'][0]:.3f} versus {m['identity_values'][1]:.3f}) and `{m['attribute_definition']}` for feature `{m['attribute']}` ({m['attribute_values'][0]:.3f} versus {m['attribute_values'][1]:.3f}). The minimum gap is {m['minimum_gap']:.3f}.",
        "",
        "This is a non-degenerate empirical witness that the two information structures are decision-incomparable. It rules out a gain-independent scalar that agrees with both decisions; it does not rule out policy-specific scalar feasibility encodings.",
        "",
        "## Population-anchor reversal",
        "",
        f"On {a['dataset_name']} (OpenML {a['dataset_id']}, n={a['records']:,}), the same exact-identity metric reverses the two releases between `{a['left_favouring_population']}` (support {a['left_anchor_support']:,}; values {a['left_anchor_values'][0]:.3f}/{a['left_anchor_values'][1]:.3f}) and `{a['right_favouring_population']}` (support {a['right_anchor_support']:,}; values {a['right_anchor_values'][0]:.3f}/{a['right_anchor_values'][1]:.3f}).",
        "",
        "## Substitution separation",
        "",
        f"On {s['dataset_name']} (OpenML {s['dataset_id']}, n={s['records']:,}), the predicted-label surface has exact identity value {s['evaluated_exact_identity_value']:.3f}, while the released leaf-signature surface has value {s['released_exact_identity_value']:.3f}. Label is a deterministic garbling of leaf signature, not conversely; assessing only labels cannot certify the fuller surface.",
        "",
        "## Validation",
        "",
        f"Independent raw-row replay passed: `{result['validation']['raw_hash_and_all_values_replayed']}`.",
    ]) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
