"""Local case preparation and assessment orchestration, never authorization.



Workspace formats are deliberately separate from registered MRAP contracts.

Documents are inventoried, not interpreted as authenticated approvals.

"""

from __future__ import annotations



import argparse

import hashlib

import importlib.metadata

import importlib.util

import json

import os

import platform

import subprocess

import sys

import uuid

from datetime import datetime, timezone

from pathlib import Path

from typing import Literal



from pydantic import BaseModel, ConfigDict, Field, model_validator



from .audit import AuditStore

from .engine import AssuranceEngine
from .errors import IntegrityError

from .models import AssessmentRequest

from .version import VERSION



KINDS = ("trained", "fine-tuned", "adapter", "merged", "ensemble", "distilled")

ROUTES = ("api", "named-party-weights", "public-weights")

SLOTS = (

    "candidate", "lineage", "request", "agency-scope", "evaluation-plan",

    "utility-report", "security-report", "independent-review",

)

EDUCATION_OPTIONAL = {"agency-scope", "security-report", "independent-review"}

Mode = Literal["review", "education"]

Kind = Literal["trained", "fine-tuned", "adapter", "merged", "ensemble", "distilled"]

Route = Literal["api", "named-party-weights", "public-weights"]





class Strict(BaseModel):

    model_config = ConfigDict(extra="forbid")





class FileBinding(Strict):

    path: str = Field(min_length=1)

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")





class Parent(FileBinding):

    parent_id: str = Field(min_length=1)





class Lineage(Strict):

    format_version: Literal["local-lineage/1"] = "local-lineage/1"

    kind: Kind

    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    parents: list[Parent]

    recipe: FileBinding

    data_manifest: FileBinding

    population_overlap: Literal["single-source", "disjoint", "overlapping", "unknown"]

    overlap_evidence: FileBinding

    previous_release_ids: list[str]



    @model_validator(mode="after")

    def validate_parents(self):

        minimum = 2 if self.kind in {"merged", "ensemble"} else (0 if self.kind == "trained" else 1)

        if len(self.parents) < minimum:

            raise ValueError(f"{self.kind} needs at least {minimum} bound parent artifact(s)")

        if len({p.parent_id for p in self.parents}) != len(self.parents):

            raise ValueError("parent identifiers must be unique")

        if len({p.sha256 for p in self.parents}) != len(self.parents):

            raise ValueError("duplicate parent bytes cannot count as different components")

        if any(p.sha256 == self.candidate_sha256 for p in self.parents):

            raise ValueError("candidate cannot be its own parent")

        if len(set(self.previous_release_ids)) != len(self.previous_release_ids):

            raise ValueError("previous release identifiers must be unique")

        if self.population_overlap == "unknown":

            raise ValueError("resolve population overlap in the protected data manifest before assessment")

        if len(self.parents) > 1 and self.population_overlap == "single-source":

            raise ValueError("multiple parents require an explicit disjoint/overlapping declaration")

        return self





class Project(Strict):

    format_version: Literal["local-workflow/1"] = "local-workflow/1"

    name: str = Field(min_length=1)

    kind: Kind

    route: Route

    mode: Mode = "review"

    files: dict[str, FileBinding | None]

    supporting_files: dict[str, FileBinding] = Field(default_factory=dict)



    @model_validator(mode="after")

    def validate_slots(self):

        if set(self.files) != set(SLOTS):

            raise ValueError("workspace must retain every required input slot")

        if set(self.supporting_files) & set(SLOTS):
            raise ValueError("supporting files cannot replace required input slots")

        return self





def digest(path: Path) -> str:

    if not path.is_file():

        raise ValueError(f"expected a regular file: {path}")

    with path.open("rb") as stream:

        return hashlib.file_digest(stream, "sha256").hexdigest()





def resolve(base: Path, ref: FileBinding) -> Path:

    path = Path(ref.path)

    return (path if path.is_absolute() else base / path).resolve()





def verified_bytes(base: Path, ref: FileBinding) -> bytes:

    path = resolve(base, ref)

    if path.stat().st_size > 10 * 1024 * 1024:

        raise ValueError("workflow JSON exceeds the 10 MiB local input limit")

    data = path.read_bytes()

    if hashlib.sha256(data).hexdigest() != ref.sha256:

        raise ValueError(f"digest mismatch: {path}")

    return data





def write_json(path: Path, value: dict, *, replace: bool = False) -> None:

    data = json.dumps(value, indent=2, allow_nan=False) + "\n"

    if not replace:

        with path.open("x", encoding="utf-8", newline="\n") as stream:

            stream.write(data)

        return

    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")

    try:

        with temporary.open("x", encoding="utf-8", newline="\n") as stream:

            stream.write(data)

        os.replace(temporary, path)

    finally:

        temporary.unlink(missing_ok=True)





def load_project(root: Path) -> Project:

    return Project.model_validate_json((root / "project.json").read_bytes())





def initialize(root: Path, kind: str, route: str, mode: Mode = "review") -> None:

    project = Project(name=root.name, kind=kind, route=route, mode=mode, files=dict.fromkeys(SLOTS))

    root.mkdir(parents=True, exist_ok=False)

    write_json(root / "project.json", project.model_dump())

    write_json(root / "lineage.template.json", {

        "format_version": "local-lineage/1", "kind": kind,

        "candidate_sha256": None, "parents": [], "recipe": None,

        "data_manifest": None, "population_overlap": "unknown",

        "overlap_evidence": None, "previous_release_ids": [],

    })

    (root / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    (root / "START-HERE.md").write_text(

        f"# {root.name}: {kind}, {route}\n\n"

        "This is an incomplete local case workspace, not approval to train or release.\n\n"

        "1. Freeze the agency scope, protected units, recipient access, authority and evaluation plan.\n"

        "2. Run approved training/evidence workers in the protected environment.\n"

        "3. Complete lineage.template.json and save it as lineage.json. Every reference has path and sha256. "

        "Paths inside lineage.json resolve relative to that file. Bind all immediate parents, "

        "the training/merge/router recipe, protected data manifest and overlap review.\n"

        "4. Bind each input with `mra-workflow bind CASE SLOT FILE`. "

        "Use `mra-workflow fingerprint FILE` for a file reference.\n"

        "5. Run `mra-workflow check CASE`; resolve missing inputs and mismatches.\n"

        "6. Run `mra-workflow assess CASE` for the existing Engine assessment and local audit.\n\n"

        f"Mode: {mode}. Required slots: " + ", ".join(slot for slot in SLOTS if mode != "education" or slot not in EDUCATION_OPTIONAL) + ".\n\n"

        "The request must be a genuine current AssessmentRequest with its original evidence "

        "paths intact; this tool does not manufacture scientific evidence. Documents are "

        "inventoried only, not authenticated approvals. Outputs require protected custody.\n\n"

        "Fine-tuning/adapters: compare base and derivative, including recipient access to the base. "

        "Merges/ensembles: compare components, combination and joint access; do not average privacy scores. "

        "Distillation: inspect teacher data/outputs and test the student. "

        "All profiles need known-leak controls, applicable ceilings and utility/subgroup tests. "
        "Education exercises may omit agency scope, security and independent-review documents; "
        "these remain necessary considerations for actual agency review.\n\n"

        "No weights are loaded, code from the case is never executed, and no model is deployed. "

        "A filename, digest or successful preflight cannot establish document adequacy.\n",

        encoding="utf-8", newline="\n",

    )





def bind(root: Path, slot: str, path: Path) -> None:

    project = load_project(root)

    if slot not in SLOTS:

        raise ValueError("unknown input slot")

    path = path.resolve()

    # The observed hash inventories bytes; it is not trusted provenance or plan approval.

    project.files[slot] = FileBinding(path=str(path), sha256=digest(path))

    if slot == "request":
        project.supporting_files.pop("training-verification", None)
        try:
            request = AssessmentRequest.model_validate_json(path.read_bytes())
        except ValueError:
            request = None  # Invalid documents remain inventoryable for preflight diagnostics.
        if request is not None and any(value.provenance.tool == "public-classifier-loss" and value.provenance.tool_version != "1.0.0" for value in request.analyzer_inputs):
            replay = path.parent / "training-verification.json"
            project.supporting_files["training-verification"] = FileBinding(path=str(replay), sha256=digest(replay))

    write_json(root / "project.json", project.model_dump(), replace=True)





def create_lineage(root: Path, parents: list[list[str]], recipe: Path, data_manifest: Path,

                   overlap_evidence: Path, population_overlap: str,

                   previous_release_ids: list[str]) -> Path:

    project = load_project(root)

    candidate = project.files["candidate"]

    if candidate is None or digest(resolve(root, candidate)) != candidate.sha256:

        raise ValueError("bind the exact candidate before building lineage")



    def reference(path: Path) -> dict:

        path = path.resolve()

        return {"path": str(path), "sha256": digest(path)}



    lineage = Lineage(

        kind=project.kind, candidate_sha256=candidate.sha256,

        parents=[Parent(parent_id=identifier, **reference(Path(path))) for identifier, path in parents],

        recipe=FileBinding(**reference(recipe)), data_manifest=FileBinding(**reference(data_manifest)),

        overlap_evidence=FileBinding(**reference(overlap_evidence)),

        population_overlap=population_overlap, previous_release_ids=previous_release_ids,

    )

    path = root / ("lineage-" + uuid.uuid4().hex + ".json")

    write_json(path, lineage.model_dump())

    bind(root, "lineage", path)

    return path





def inspect_project(root: Path) -> tuple[dict, AssessmentRequest | None, Path | None]:

    project = load_project(root)

    issues: list[str] = []

    warnings: list[str] = []

    for slot, ref in {**project.files, **project.supporting_files}.items():

        if ref is None:

            if project.mode == "education" and slot in EDUCATION_OPTIONAL:

                warnings.append(f"optional educational input omitted: {slot}")

            else:

                issues.append(f"missing input: {slot}")

            continue

        try:

            if digest(resolve(root, ref)) != ref.sha256:

                issues.append(f"digest mismatch: {slot}")

        except (OSError, ValueError) as exc:

            issues.append(f"{slot}: {exc}")

    request = None

    request_base = None

    candidate = project.files["candidate"]

    lineage = None

    ref = project.files["lineage"]

    if ref is not None:

        try:

            lineage = Lineage.model_validate_json(verified_bytes(root, ref))

            if lineage.kind != project.kind or candidate is None or lineage.candidate_sha256 != candidate.sha256:

                raise ValueError("lineage kind/candidate does not match the workspace")

            base = resolve(root, ref).parent

            for source in [*lineage.parents, lineage.recipe, lineage.data_manifest, lineage.overlap_evidence]:

                if digest(resolve(base, source)) != source.sha256:

                    raise ValueError(f"lineage source digest mismatch: {source.path}")

        except (OSError, ValueError) as exc:

            issues.append(f"lineage: {exc}")

    ref = project.files["request"]

    if ref is not None:

        try:

            request = AssessmentRequest.model_validate_json(verified_bytes(root, ref))

            request_base = resolve(root, ref).parent

            release = request.release

            if candidate is None or release.artifact_sha256 != candidate.sha256:

                raise ValueError("assessment request targets a different candidate")

            if digest(resolve(request_base, FileBinding(path=release.artifact_path, sha256=release.artifact_sha256))) != release.artifact_sha256:

                raise ValueError("request artifact bytes differ from the candidate")

            if project.route != "api" and release.interface.access != "full_artifact":

                raise ValueError("weight release requires full_artifact evidence, not API evidence")

            if project.route == "api" and (

                release.interface.access in {"weights", "full_artifact"}

                or release.interface.output_channels.parameters

            ):

                raise ValueError("API route cannot describe exported model weights/parameters")

            if lineage is not None and set(lineage.previous_release_ids) != set(release.previous_release_ids):

                raise ValueError("request and lineage disagree on previous releases")

            from .registered_training import verify_local_training_evidence
            replay = project.supporting_files.get("training-verification")
            verify_local_training_evidence(request, request_base, replay.sha256 if replay else None, ref.sha256)

        except (OSError, ValueError, IntegrityError, KeyError, TypeError) as exc:

            issues.append(f"request: {exc}")

    return {

        "format_version": "local-workflow-check/1", "kind": project.kind,

        "route": project.route, "status": "inputs_incomplete" if issues else "inputs_complete",

        "issues": issues, "warnings": warnings, "mode": project.mode, "authorization_eligible": False,

        "document_adequacy_verified": False, "production_controls_verified": False,

        "note": "Preflight checks file bindings and local lineage only; the Engine must assess evidence.",

    }, request, request_base





def assess(root: Path) -> Path:

    # Unique output directories preserve previous and failed attempts.

    runs = root / "runs"

    runs.mkdir(exist_ok=True)

    run = runs / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex)

    run.mkdir()

    project_bytes = (root / "project.json").read_bytes()

    (run / "project.snapshot.json").write_bytes(project_bytes)

    try:

        preflight, request, base = inspect_project(root)

        write_json(run / "preflight.json", preflight)

        if preflight["issues"] or request is None or base is None:

            raise ValueError("preflight failed; see preflight.json and resolve inputs before retrying")

        audit = AuditStore(run / "audit.sqlite3")

        intent = audit.append_assessment_intent(request)

        try:

            report = AssuranceEngine().assess(request, base)

            after, _, _ = inspect_project(root)

            if after["issues"] or (root / "project.json").read_bytes() != project_bytes:

                raise ValueError("workspace inputs changed during assessment")

        except Exception as exc:

            audit.append_assessment_failed(intent, type(exc).__name__, str(exc)[:4096])

            raise

        audit.append_assessment_completed(intent, report)

        write_json(run / "assessment-report.json", report.model_dump(mode="json"))

        write_json(run / "audit-verification.json", audit.verify(require_events=True, require_complete=True).model_dump(mode="json"))

        write_json(run / "runtime.json", doctor())

        result = {

            "format_version": "local-workflow-result/1", "workflow_status": "assessment_recorded",

            "assessment_verdict": report.overall_verdict, "authorization_eligible": False,

            "mode": preflight["mode"], "warnings": preflight["warnings"],

            "authorized": False, "deployed": False,

            "next_step": "Independent review and external authorization; missing ceilings require new evidence or redesign.",

            "boundary": "Local orchestration, not an authenticated MRAP lifecycle transcript or complete evidence archive.",

        }

        (run / "START-HERE.md").write_text(

            f"# Assessment recorded\n\nMode: {preflight['mode']}. See preflight.json for omitted optional documents.\n\nEngine verdict: **{report.overall_verdict}**. "

            "No authorization or deployment occurred.\n\n"

            "Read assessment-report.json for threat evidence, preflight.json for input bindings, "

            "and audit-verification.json for local audit integrity. project.snapshot.json retains "

            "file references; source evidence remains in its original protected location. "

            "Arrange independent custody/replay and agency review before any release.\n",

            encoding="utf-8", newline="\n",

        )

        # Publish completion last; partial output files cannot claim completion.

        write_json(run / "workflow-result.json", result)

    except Exception as exc:

        write_json(run / "workflow-result.json", {

            "format_version": "local-workflow-result/1", "workflow_status": "failed",

            "error_type": type(exc).__name__, "authorization_eligible": False,

            "authorized": False, "deployed": False,

            "next_step": "Inspect the protected preflight/audit records, correct inputs and start a new run.",

        }, replace=True)

        raise ValueError(f"workflow failed; retained attempt: {run}; {exc}") from exc

    return run





def doctor() -> dict:

    dependencies = {}

    for name in ("pydantic", "cryptography", "numpy", "pandas", "scipy", "scikit-learn", "xgboost", "pyarrow", "joblib"):

        try:

            dependencies[name] = importlib.metadata.version(name)

        except importlib.metadata.PackageNotFoundError:

            dependencies[name] = None

    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),

            "library_version": VERSION, "dependencies": dependencies,

            "authorization_eligible": False, "trusted_runtime_attestation": False}





def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(description=__doc__, prog="mra-workflow")

    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create an incomplete release case; never overwrite")

    init.add_argument("case", type=Path)

    init.add_argument("--kind", choices=KINDS, default="trained")

    init.add_argument("--route", choices=ROUTES, default="named-party-weights")

    init.add_argument("--mode", choices=("review", "education"), default="review")

    binding = commands.add_parser("bind", help="inventory a file's current bytes; not approval")

    binding.add_argument("case", type=Path)

    binding.add_argument("slot", choices=SLOTS)

    binding.add_argument("file", type=Path)

    fingerprint = commands.add_parser("fingerprint", help="print a file reference for lineage")

    fingerprint.add_argument("file", type=Path)

    lineage = commands.add_parser("lineage", help="build and bind immediate-parent lineage from files")

    lineage.add_argument("case", type=Path)

    lineage.add_argument("--parent", nargs=2, action="append", default=[], metavar=("ID", "FILE"))

    lineage.add_argument("--recipe", type=Path, required=True)

    lineage.add_argument("--data-manifest", type=Path, required=True)

    lineage.add_argument("--overlap-evidence", type=Path, required=True)

    lineage.add_argument("--population-overlap", choices=("single-source", "disjoint", "overlapping"), required=True)

    lineage.add_argument("--previous-release", action="append", default=[])

    for name in ("check", "assess"):

        command = commands.add_parser(name)

        command.add_argument("case", type=Path)

    commands.add_parser("doctor", help="report local runtime/dependency versions")

    demo = commands.add_parser("demo", help="run the existing offline XGBoost teaching pipeline (source checkout)")

    demo.add_argument("--output", type=Path, required=True)

    args = parser.parse_args(argv)

    try:

        if args.command == "init":

            initialize(args.case.resolve(), args.kind, args.route, args.mode)

            print(str((args.case / "START-HERE.md").resolve()))

        elif args.command == "bind":

            bind(args.case.resolve(), args.slot, args.file)

            print("File bound; document adequacy and source authority remain unverified.")

        elif args.command == "fingerprint":

            print(json.dumps({"path": str(args.file.resolve()), "sha256": digest(args.file.resolve())}, indent=2))

        elif args.command == "lineage":

            print(str(create_lineage(args.case.resolve(), args.parent, args.recipe, args.data_manifest,

                                     args.overlap_evidence, args.population_overlap, args.previous_release)))

        elif args.command == "check":

            result, _, _ = inspect_project(args.case.resolve())

            print(json.dumps(result, indent=2))

            return 2 if result["issues"] else 0

        elif args.command == "assess":

            print(str(assess(args.case.resolve()) / "START-HERE.md"))

        elif args.command == "doctor":

            print(json.dumps(doctor(), indent=2))

        elif args.command == "demo":

            script = Path(__file__).resolve().parents[2] / "scripts" / "run_training_release_demo.py"

            if not script.is_file():

                raise ValueError("demo requires the source checkout; installed package supports init/bind/check/assess")

            missing = [name for name in ("numpy", "pandas", "scipy", "sklearn", "xgboost", "pyarrow", "joblib") if importlib.util.find_spec(name) is None]

            if missing:

                raise ValueError("training dependencies missing: " + ", ".join(missing) + "; run setup_pipeline.py --profile training")

            env = os.environ.copy()

            env["PYTHONPATH"] = str(script.parent.parent / "src")

            return subprocess.run([sys.executable, str(script), "--dataset-profile", "sklearn-breast-cancer", "--run-dir", str(args.output.resolve())], env=env, check=False).returncode

        return 0

    except (OSError, ValueError, RuntimeError) as exc:

        print(f"error: {exc}", file=sys.stderr)

        return 2





if __name__ == "__main__":

    raise SystemExit(main())

