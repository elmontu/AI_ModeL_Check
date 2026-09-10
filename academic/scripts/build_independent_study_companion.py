"""Export fresh study summaries and every model/candidate row without refitting."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(run):
    load = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    complete, verification, summary = load("COMPLETE.json"), load("VERIFIED.json"), load("summary.json")
    if not verification["passed"] or verification["complete_sha256"] != sha(run / "COMPLETE.json"):
        raise ValueError("independent verification is missing or does not bind this completed run")
    if complete["summary_sha256"] != sha(run / "summary.json"):
        raise ValueError("summary differs from completion manifest")
    records = []
    for relative, digest in sorted(complete["record_sha256s"].items()):
        if sha(run / relative) != digest:
            raise ValueError("model record changed: " + relative)
        records.append({"source_path": str((run / relative).relative_to(ROOT)).replace("\\", "/"),
                        "source_sha256": digest, **load(relative)})
    names = ("FROZEN.json", "STARTED.json", "COMPLETE.json", "VERIFIED.json", "registration.json", "summary.json", "runner.py", "verifier.py")
    data = {"study_id": load("registration.json")["study_id"],
        "source_records": [{"path": str((run / name).relative_to(ROOT)).replace("\\", "/"), "sha256": sha(run / name)} for name in names],
        "registration": load("registration.json"), "verification": verification, "summary": summary,
        "model_records": records, "availability": "This companion ships aggregate/model-level records; original artifacts and retained draws are in the named local source directory. Independent public access is not asserted."}
    lookup = {(r["family"], r["regime"], r["method"]): r for r in summary["groups"]}
    text = [r"\begin{table*}[t]", r"\centering\footnotesize",
        r"\caption{New synthetic study: 84 independent trained models per family; regimes and controls are paired within models. Useful means the selected candidate satisfies exact oracle privacy and utility constraints. Point-error columns count model/regime selections, not independent repeated trials.}",
        r"\label{tab:independent-models}",
        r"\begin{tabular}{@{}llrrrrr@{}}", r"\toprule",
        r"Family & Regime & Oracle feasible & Bound useful & Point useful & Point privacy errors & Point utility errors \\", r"\midrule"]
    families = {"logistic": "Logistic", "cart_depth2": "Depth-2 tree"}
    regimes = {"low_leakage": "Low leakage", "boundary_safe": "Boundary-safe", "boundary_stress": "Boundary stress", "high_leakage": "High leakage"}
    for family, label in families.items():
        for regime, regime_label in regimes.items():
            bound, point = (lookup[family, regime, method] for method in ("simultaneous_bounds", "point_estimates"))
            text.append(f"{label} & {regime_label} & {bound['oracle_feasible']} & {bound['useful_selection']} & {point['useful_selection']} & {point['privacy_violation']} & {point['utility_violation']} " + r"\\")
    text.extend([r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode(), "\n".join(text).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data, tables = build(args.run_directory.resolve())
    for name, payload in (("independent-model-study-data.json", data), ("independent-model-study-tables.tex", tables)):
        path = ROOT / "academic/paper" / name
        if args.check:
            if path.read_bytes() != payload:
                raise ValueError("companion does not replay: " + name)
        else:
            with path.open("xb") as output:
                output.write(payload)
    print("Independent-study companion and tables " + ("replay exactly" if args.check else "written; historical companion unchanged"))


if __name__ == "__main__":
    main()
