#!/usr/bin/env python3
"""Extract source-addressable aggregate paper data; never run an experiment.

Only the explicitly selected public aggregate fields below may be exported.
Ignored local sources remain local-only evidence, not a portable release seal.
JSON pointers are RFC 6901 pointers into the exact bytes named by each source.
Markdown table values preserve their published precision and line locations.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "academic" / "paper" / "experimental-data.json"
HOOK_AUDIT = "docs/real-data-training-hook-audit-2026-09-02.md"
LOCAL = "output/public-data-validation-20260906"
BENCH = "output/mrap-e2e-20260907/benchmark"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
FORBIDDEN_FIELDS = {
    "raw_scores", "target_member_losses", "target_nonmember_losses",
    "calibration_member_losses", "calibration_nonmember_losses", "observations",
    "text", "prompt", "response", "token_ids", "row_ids", "record_ids",
    "stdout", "stderr", "traceback", "cwd", "executable", "command",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(raw: bytes):
    def invalid(value):
        raise ValueError(f"nonfinite JSON number: {value}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=invalid)


def pointer_get(value, pointer: str):
    for component in pointer.lstrip("/").split("/") if pointer else ():
        key = component.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def public_value(value: Any) -> Any:
    """Reject, rather than silently redact, accidental non-aggregate selections."""
    if isinstance(value, dict):
        bad = FORBIDDEN_FIELDS.intersection(value)
        if bad:
            raise ValueError(f"non-public selected field: {sorted(bad)}")
        return {key: public_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, str) and re.search(r"(?:\b[A-Za-z]:[\\/]|/Users/|/home/|/mnt/)", value):
        raise ValueError("absolute host path in selected aggregate")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite selected aggregate")
    return value


class Builder:
    def __init__(self):
        self.sources: dict[str, dict] = {}
        self.payloads: dict[str, Any] = {}
        self.raw: dict[str, bytes] = {}
        self.tables: list[dict] = []
        self.checks: list[dict] = []
        self.exclusions: list[dict] = []

    def source(self, key, relative, *, status, vintage, limitations=(), optional=False):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("source escapes repository")
        if not path.exists() and optional:
            self.exclusions.append({"path": relative, "status": "not_available_locally",
                                    "reason": "No completed report available at this inventory path."})
            return None
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(f"source exceeds bounded read cap: {relative}")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("source grew beyond bounded read cap")
        self.sources[key] = {"id": key, "path": relative, "sha256": digest(raw),
            "bytes": len(raw), "storage": "ignored_local_only" if relative.startswith("output/") else "tracked",
            "status": status, "vintage": vintage, "limitations": list(limitations)}
        self.raw[key] = raw
        self.payloads[key] = parse(raw) if path.suffix == ".json" else None
        return self.payloads[key]

    def bound_file(self, key, relative, expected, *, status="bound_supporting_artifact", vintage="historical"):
        self.source(key, relative, status=status, vintage=vintage)
        self.require(self.sources[key]["sha256"] == expected, key + ": expected SHA-256")

    def require(self, condition, description):
        if not condition:
            raise ValueError(description)
        self.checks.append({"check": description, "passed": True})

    def table(self, key, source, pointer, *, fields=None, note="", singleton=False, mapping=False):
        collection = pointer_get(self.payloads[source], pointer)
        if singleton:
            collection = [collection]
        if not isinstance(collection, dict if mapping else list):
            raise ValueError(f"expected aggregate row list at {source}{pointer}")
        rows = []
        for index, row in collection.items() if mapping else enumerate(collection):
            index = escape(str(index))
            base = pointer if singleton else f"{pointer}/{index}"
            if not isinstance(row, dict):
                raise ValueError("table row is not an object")
            selected = list(row) if fields is None else fields
            values, locations = {}, {}
            for field in selected:
                value = pointer_get(row, "/" + field)
                values[field] = public_value(value)
                locations[field] = base + "/" + field
            rows.append({"source_pointer": base, "values": values, "field_pointers": locations})
        self.tables.append({"id": key, "source_id": source, "source_pointer": pointer,
                            "interpretation": note, "row_count": len(rows), "rows": rows})

    def markdown_tables(self, key):
        lines = self.raw[key].decode("utf-8").splitlines()
        heading, number = "", 0
        i = 0
        while i < len(lines):
            if lines[i].startswith("#"):
                heading = lines[i].lstrip("# ")
            if (i + 1 < len(lines) and lines[i].startswith("|") and
                    re.fullmatch(r"[|:\-\s]+", lines[i + 1])):
                headers = [part.strip() for part in lines[i].strip().strip("|").split("|")]
                number += 1
                start = i + 1
                i += 2
                rows = []
                while i < len(lines) and lines[i].startswith("|"):
                    cells = [part.strip() for part in lines[i].strip().strip("|").split("|")]
                    if len(cells) != len(headers):
                        raise ValueError(f"unexpected Markdown table width at line {i+1}")
                    rows.append({"source_line": i + 1,
                                 "values": public_value(dict(zip(headers, cells))),
                                 "precision": "exact published strings; numerical displays may be rounded"})
                    i += 1
                self.tables.append({"id": f"hook_audit_table_{number:02}", "source_id": key,
                    "section": heading, "header_line": start, "columns": headers,
                    "row_count": len(rows), "rows": rows,
                    "interpretation": "Curated historical aggregate record; original internal reports are not retained here."})
            else:
                i += 1

    def manifest_entries(self, source, pointer, parent, prefix):
        entries = pointer_get(self.payloads[source], pointer)
        for index, entry in enumerate(entries):
            self.bound_file(f"{prefix}_{index:02}", str(Path(parent, entry["path"]).as_posix()), entry["sha256"])
            if "bytes" in entry:
                self.require(self.sources[f"{prefix}_{index:02}"]["bytes"] == entry["bytes"],
                             f"{prefix}_{index:02}: expected byte count")


def retained_studies(b):
    b.source("publication_validator", "scripts/summarize_ceiling_experiments.py",
             status="extraction_time_aggregate_validator_not_historical_measurement",
             vintage="current extraction source")
    sources = (
        ("controlled", "reproduction/finite-channel-ceiling/results/ground-truth-report.json", "completed_acceptance_passed", "2026-09-03; dd08baa3 source"),
        ("model_v2", "reproduction/model-backed-finite-channel/results/v2/model-backed-finite-channel-report.json", "completed_acceptance_failed_8_of_9", "2026-09-03 v2 predecessor"),
        ("model_v3", "reproduction/model-backed-finite-channel/results/v3/model-backed-finite-channel-report.json", "completed_acceptance_passed_10_of_10", "2026-09-03 prospective corrective v3; f98baa46 source"),
    )
    limits = ["Historical implementation, not current 0.8 validation or authorization.",
              "Finite registered channels/pools; no whole-world threat or endpoint adequacy proof.",
              "Legacy production_* field names denote the reference analyzer, not deployed production."]
    for key, path, status, vintage in sources:
        obj = b.source(key, path, status=status, vintage=vintage, limitations=limits)
        manifest = b.source(key + "_manifest", str(Path(path).parent / "manifest.json").replace("\\", "/"),
                            status="retained_integrity_manifest", vintage=vintage)
        field = "ground_truth_report_sha256" if key == "controlled" else "report_sha256"
        b.require(manifest["retained_artifacts"][field] == b.sources[key]["sha256"], key + ": manifest report binding")
    spec = importlib.util.spec_from_file_location(
        "academic_publication_validator", ROOT / "scripts" / "summarize_ceiling_experiments.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the shared publication-summary validator")
    summary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summary)
    summary.build_publication_summary(b.payloads["controlled"], b.payloads["model_v3"],
        known_report_sha256=b.sources["controlled"]["sha256"],
        model_report_sha256=b.sources["model_v3"]["sha256"],
        predecessor_model_report=b.payloads["model_v2"],
        predecessor_model_report_sha256=b.sources["model_v2"]["sha256"])
    b.checks.append({"check": "existing publication-summary validator accepts all three source families", "passed": True})
    b.table("controlled_groups", "controlled", "/groups", note="All 9 groups; tier_role distinguishes primary from diagnostic.")
    b.table("controlled_headline", "controlled", "/headline", singleton=True)
    b.table("controlled_performance", "controlled", "/performance", singleton=True)
    b.table("controlled_completion", "controlled", "/completion", singleton=True)
    b.table("controlled_repeat_records", "controlled", "/raw_count_records",
            note="1,800 aggregate multinomial/count replay records, not individual data examples.")
    for key in ("model_v2", "model_v3"):
        b.table(key + "_primary", key, "/results")
        b.table(key + "_repeated_summary", key, "/repeated_validation/summaries")
        b.table(key + "_acceptance", key, "/acceptance", singleton=True)
        b.table(key + "_erasure", key, "/erasure_comparisons")
        obj = b.payloads[key]
        parent = Path(b.sources[key]["path"]).parent
        for index, row in enumerate(obj["repeated_validation"]["summaries"]):
            family = next(item for item in obj["results"] if item["collector_model"] == row["collector_model"] and item["variant_id"] == row["variant_id"])
            source = f"{key}_repeats_{index}"
            b.bound_file(source, (parent / family["artifact_directory"] / row["retained_rows_path"]).as_posix(), row["retained_rows_sha256"])
            b.table(source, source, "/rows", note="200 conditional finite-pool aggregate replays; not 200 trained models.")
    b.source("hook_audit", HOOK_AUDIT, status="curated_completed_historical_execution",
             vintage="2026-09-02 NVIDIA L4; rounded publication tables",
             limitations=["Internal JSON reports are represented by recorded digests, not available replayable files.",
                          "One seed/epoch; descriptive screens; no MRA assessment input or release authority."])
    b.markdown_tables("hook_audit")


def model_scaling(b):
    manifest = b.source("local_scaling_manifest", LOCAL + "/RESULTS-MANIFEST.json", optional=True,
        status="local_completed_aggregate_manifest", vintage="2026-09-06/07 before 0.8 remediation")
    if manifest is None:
        return
    for key, entry in manifest["reports"].items():
        b.bound_file("local_" + key, f"{LOCAL}/{entry['path']}", entry["sha256"], vintage="2026-09-06/07 pre-remediation local Windows run")
    for index, (path, entry) in enumerate(manifest["supporting_artifacts"].items()):
        b.bound_file(f"local_support_{index:02}", f"{LOCAL}/{path}", entry["sha256"])
        b.require(b.sources[f"local_support_{index:02}"]["bytes"] == entry["bytes"], f"local support {path}: byte count")
    b.table("tree_primary", "local_tree", "/results")
    b.table("tree_timing_repeats", "local_tree_repeats", "/results",
            note="Nine same-seed repeated timings; duplicated statistical outcomes are not new evidence.")
    b.table("tree_timing_summary", "local_tree_repeats", "/summary", mapping=True,
            fields=["completed", "model_hashes"] + [f"{metric}/{stat}" for metric in
                ("training_wall_seconds", "training_rows_per_second", "training_sampled_peak_working_set_bytes", "prediction_seconds", "privacy.elapsed_seconds", "privacy.scoring_rows_per_second")
                for stat in ("median", "minimum", "maximum")])
    b.table("vision_scaling", "local_vision", "/cells")
    b.table("llm_scaling", "local_llm", "/cells")
    b.table("vision_runtime", "local_vision", "/runtime", singleton=True,
            fields=["cpu_threads", "cuda_runtime", "cudnn", "gpu", "gpu_total_bytes", "local_experiment_not_frozen_ec2_replay", "platform", "python", "torch", "torchvision"])
    b.table("llm_runtime", "local_llm", "/runtime", singleton=True,
            fields=["gpu", "initial_cuda_free_and_total_bytes", "platform", "python", "versions"])
    for key in ("local_tree", "local_tree_repeats", "local_vision", "local_llm"):
        b.sources[key]["limitations"] = b.payloads[key].get("limitations", [])
        b.sources[key]["status"] = "completed_local_aggregate_not_portable_full_reproduction"
    for key in ("local_tree", "local_tree_repeats"):
        b.require(b.payloads[key]["all_cases_completed"] and not b.payloads[key]["failures"], key + ": every declared case completed")
    b.require(len(b.payloads["local_vision"]["cells"]) == 6, "local vision: all 6 cells present")
    b.require(b.payloads["local_llm"]["status"] == "completed" and b.payloads["local_llm"]["completed_cells"] == 6, "local LLM: all 6 cells completed")
    b.source("llm_completion", LOCAL + "/llm/scaling-run-v2/RUN_COMPLETE.json", status="local_completion_manifest", vintage="2026-09-06")
    b.manifest_entries("llm_completion", "/artifacts", LOCAL + "/llm/scaling-run-v2", "llm_complete_file")
    for key, path in (("vision_verification", "vision/results/verification.json"),
                      ("tree_timing_verification", "tree/isolated-timing-replay/verification.json"),
                      ("llm_verification", "llm/scaling-run-v2.verification.json")):
        b.source(key, LOCAL + "/" + path, status="historical_independent_replay_receipt", vintage="2026-09-06/07")
    b.table("vision_verification", "vision_verification", "", singleton=True)
    b.table("llm_verified_cells", "llm_verification", "/cells")
    b.table("historical_tests", "local_tests", "", fields=["started_at", "finished_at", "tests_run", "passed", "software"], singleton=True,
            note="136 entries: 132 passed, 1 failure and 3 errors; not current validation.")
    for kind in ("failures", "errors", "skipped"):
        if kind in b.payloads["local_tests"] and b.payloads["local_tests"][kind]:
            b.table("historical_test_" + kind, "local_tests", "/" + kind, fields=["test"],
                    note="Raw tracebacks excluded because they contain absolute host paths. Failure identities are preserved.")


def cli_benchmark(b):
    report = b.source("cli_summary", BENCH + "/summary.json", optional=True,
        status="completed_historical_synthetic_benchmark", vintage="0145b3c pre-0.8 remediation",
        limitations=["33 timing repetitions, not 33 independent privacy studies.",
                     "Synthetic repeated threats, duplicate-interface candidates, padded artifacts, locally held role keys.",
                     "No training, scientific collection, registry service or serving gateway.",
                     "peak_cli_child_mib measured a launcher and is excluded from interpreter-memory claims."])
    if report is None:
        return
    b.source("cli_plan", BENCH + "/plan.json", status="historical_frozen_plan", vintage="0145b3c")
    b.require(b.sources["cli_plan"]["sha256"] == report["plan_sha256"], "CLI timing plan binding")
    b.table("cli_timing_profiles", "cli_summary", "/profiles", fields=["profile", "actual_audit_events", "actual_transcript_events", "chain_seconds", "stage_seconds"])
    b.table("excluded_launcher_memory", "cli_summary", "/profiles", fields=["profile", "peak_cli_child_mib"],
            note="INVALID FOR CLI INTERPRETER MEMORY: measures launcher process only; retained to expose correction.")
    receipt = b.source("cli_verification", BENCH + "/verification.json", status="historical_independent_replay_receipt", vintage="0145b3c")
    b.require(report["all_33_cases_passed"] and report["total_cli_commands"] == 297, "33 timing cases and 297 CLI calls recorded")
    runs, stages = [], []
    for item in receipt["cases"]:
        name = item["case"]
        source = "cli_run_" + name
        b.bound_file(source, f"{BENCH}/timed-runs/{name}/result.json", item["result_sha256"], vintage="0145b3c")
        b.table(source, source, "", singleton=True, fields=["profile", "actual_audit_events", "actual_transcript_events", "expected_statuses_verified", "measured_cli_chain_seconds", "production_authorization_issued"])
        runs.extend([{**row, "source_id": source} for row in b.tables.pop()["rows"]])
        b.table(source + "_stages", source, "/steps", fields=["stage", "started_at_utc", "exit_code", "wall_seconds"])
        stages.extend([{**row, "source_id": source} for row in b.tables.pop()["rows"]])
    b.tables.append({"id": "cli_timing_runs", "row_count": len(runs), "rows": runs, "interpretation": "Three frozen repetitions per profile; original per-run durations."})
    b.tables.append({"id": "cli_timing_stages", "row_count": len(stages), "rows": stages, "interpretation": "297 original CLI stage timing observations."})
    b.source("cli_memory", BENCH + "/memory-summary.json", status="completed_corrected_interpreter_memory_supplement", vintage="0145b3c",
             limitations=["One observation per largest-axis profile, no variance estimate; includes wrapper overhead, excludes parent/prefix processes."])
    b.table("cli_interpreter_memory", "cli_memory", "/profiles")
    b.require(b.payloads["cli_memory"]["all_6_cases_passed"] and b.payloads["cli_memory"]["cli_commands"] == 54,
              "corrected interpreter memory: 6 cases and 54 CLI calls recorded")
    b.source("cli_memory_verification", BENCH + "/memory-verification.json", status="historical_memory_replay_receipt", vintage="0145b3c")


def supplementary(b):
    for index, path in enumerate(("output/public-privacy-audit/privacy-audit-report.json", "output/public-privacy-audit/0aa761f3b1311a03/privacy-audit-report.json")):
        key = f"legacy_privacy_{index}"
        obj = b.source(key, path, optional=True, status="local_report_without_completion_seal_or_verified_registration", vintage="legacy v1; report omits execution timestamp",
            limitations=["Historical descriptive audit only; no completed publication bundle or current-source binding.",
                         "Pooled equal-class Clopper-Pearson claim is not accepted as a verified binomial bound; group success probabilities may differ.",
                         "Multiple models lack a verified simultaneous selection family; raw scores excluded."])
        if obj is None:
            continue
        b.table(key, key, "/models", fields=["model", "training_rows", "utility_accuracy", "attack/attack", "attack/member_trials", "attack/nonmember_trials", "attack/true_members", "attack/true_nonmembers", "attack/successes", "attack/trials", "attack/equal_prior_success", "attack/one_sided_95pct_clopper_pearson_lower", "attack/advantage_over_random"],
            note="Descriptive reported values only. The reported pooled confidence endpoint is NOT endorsed or usable for paper soundness claims.")
    for key, path in (("strategic_full", "output/reproduction/strategic-assurance-experiment.json"), ("strategic_smoke", "output/reproduction/strategic-assurance-smoke.json")):
        obj = b.source(key, path, optional=True, status="local_synthetic_stress_test_report", vintage="historical report; no execution timestamp or source freeze",
            limitations=["Synthetic payoff intervals; no behavioral, institutional or deployment validation.", "Seeded grid samples are not proof of universal validity or independent replications."])
        if obj is not None:
            b.table(key, key, "/sample_results")
            b.table(key + "_validation", key, "/validation", singleton=True)
            b.table(key + "_frontier", key, "/submitter_deterrence_frontier")
    obj = b.source("synthetic_workflow", "output/model-audit-workflow/report.json", optional=True,
        status="synthetic_functional_rehearsal_not_empirical_training", vintage="legacy sample workflow",
        limitations=["Hand-built model fixtures and a few synthetic functional cases; not a model training/privacy result."])
    if obj is not None:
        b.table("synthetic_workflow", "synthetic_workflow", "/models", fields=["experiment_id", "kind", "functional_evaluation/metric", "functional_evaluation/value", "functional_evaluation/cases", "can_clear"])
    current = "output/track-split-20260907/tests-20260907T034228.335093Z/results.json"
    if b.source("current_software_tests", current, optional=True, status="software_regression_validation_not_privacy_experiment", vintage="0.8 track split before paper changes") is not None:
        b.table("current_software_tests", "current_software_tests", "", singleton=True)
    proof = b.source("supplementary_proof_receipt", "output/mrap-e2e-20260907/proof/PROOF_COMPLETE.json", optional=True,
        status="historical_kernel_build_receipt_not_new_build", vintage="2026-09-07 supplementary target abstraction",
        limitations=["63 theorem count includes 39 existing and 24 supplementary; no Python refinement or world-adequacy proof."])
    if proof is not None:
        for index, (path, expected) in enumerate(proof["artifact_sha256"].items()):
            b.bound_file(f"proof_artifact_{index}", "output/mrap-e2e-20260907/proof/" + path, expected)
        b.table("supplementary_proof_receipt", "supplementary_proof_receipt", "", singleton=True,
                fields=["status", "existing_audited_theorems", "supplement_audited_theorems", "total_audited_theorems", "toolchain", "permitted_axioms", "python_refinement_proved", "production_service_refinement_proved", "real_world_taxonomy_adequacy_proved", "four_verdict_function_is_target_specification_only", "historical_attempts_preserved"])


def build():
    b = Builder()
    retained_studies(b)
    model_scaling(b)
    cli_benchmark(b)
    supplementary(b)
    b.exclusions.extend([
        {"path": "reproduction/openml", "status": "registered_design_only", "reason": "No full retained generated study, trained artifacts, witness bundle, or final seal in available output inventory."},
        {"path": "reproduction/composition-scaling", "status": "configured_only", "reason": "No completed 165-cell five-model suite found. Configurations and unit checks are not executed-study evidence."},
        {"path": "reproduction/portfolio-stochastic", "status": "configured_only", "reason": "No generated stochastic benchmark result found in output/reproduction or top-level output directories."},
        {"path": "reproduction/model-audit-workflow/empirical-xgboost-mlp-config.json", "status": "configured_only", "reason": "No completed empirical XGBoost/MLP repeated-study report found; synthetic sample workflow is separate."},
        {"path": LOCAL + "/vision/draft-plan-v1-no-training-executed.json", "status": "superseded_unexecuted_draft", "reason": "Do not count preparation revisions or the failed pretraining metadata-race attempt as trained cells."},
        {"path": "output/mrap-counterproofs-20260907", "status": "separate_counterexample_artifacts", "reason": "Adversarial fixtures are handled by the proof/counterexample contribution, not counted as empirical privacy experiments."},
    ])
    for source in b.sources.values():
        b.require(digest((ROOT / source["path"]).read_bytes()) == source["sha256"], source["id"] + ": source unchanged during extraction")
    return {"schema_version": "1.0", "artifact_role": "aggregate_academic_paper_companion_not_MRAP_contract",
        "generator": {"path": "academic/scripts/build_academic_paper_data.py", "sha256": digest(Path(__file__).read_bytes())},
        "source_policy": "Explicit allowlist; no network, training, raw examples, model weights or historical edits. Ignored sources are not supplied by a clean clone.",
        "pointer_semantics": "field_pointers address exact JSON source values; nested values retain names. Markdown rows carry one-based source lines and published precision.",
        "inventory_scope": {"root": "output", "named_local_report_roots": ["public-data-validation-20260906", "public-privacy-audit", "reproduction", "model-audit-workflow", "mrap-e2e-20260907", "track-split-20260907"],
            "method": "Bounded named-study report/summary/completion inventory, excluding caches, raw datasets, model snapshots and generated fixture trees; not a claim that every workstation artifact was searched."},
        "sources": list(b.sources.values()), "tables": b.tables, "exclusions": b.exclusions,
        "validation": {"checks": b.checks, "experiments_rerun": False, "proofs_rebuilt": False,
            "all_results_current_version": False, "publication_bundle_complete": False,
            "authorization_eligible": False, "historical_negative_results_preserved": True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Rebuild from all available named sources and compare exact generated bytes; missing local sources do not constitute a complete replay.")
    args = parser.parse_args()
    data = build()
    destination = args.output.resolve()
    protected_sources = {(ROOT / source["path"]).resolve() for source in data["sources"]}
    protected_sources.add(Path(__file__).resolve())
    if destination in protected_sources:
        raise SystemExit("refusing to overwrite an experimental source or the generator")
    payload = (json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if args.check:
        if not args.output.exists() or args.output.read_bytes() != payload:
            raise SystemExit("paper data differs or required local sources are unavailable; no evidence was rewritten")
        action = "verified"
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=args.output.parent, prefix=".paper-data-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, args.output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        action = "generated"
    print(json.dumps({"action": action, "sources": len(data["sources"]), "tables": len(data["tables"]),
        "rows": sum(table["row_count"] for table in data["tables"]), "sha256": digest(payload), "bytes": len(payload)}, sort_keys=True))


if __name__ == "__main__":
    main()
