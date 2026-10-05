"""Provenance catalog, independent of data loading and optional ML libraries.

A listed registration is not a completed experiment or an available local dataset.
The pinned OpenML metadata establishes a reviewed repository identity only, not
upstream authenticity, licensing approval, or authority to release a model.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

OPENML_MANIFEST = Path("reproduction/openml/manifests/suite-99-datasets.json")
MAX_MANIFEST_BYTES = 1024 * 1024
# Semantic digest of the retained registration manifest; whitespace is immaterial.
_OPENML_SHA256 = "4e651068698e8ea9505aca4e747bedaa78e89c7ab7a8d40773682ad9a18c794c"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MD5 = re.compile(r"[0-9a-f]{32}\Z")
_TOP_FIELDS = frozenset(("config_path", "config_sha256", "configured_dataset_count",
    "created_at", "datasets", "failed_dataset_count", "failures", "manifest_version",
    "runtime", "study_alias", "study_id", "study_sha256", "study_url", "successful_dataset_count"))
_DATASET_FIELDS = frozenset(("class_counts", "classes", "dataset_id", "feature_dtypes",
    "feature_names", "features", "file_id", "missing_feature_values", "name", "openml_md5_checksum",
    "openml_url", "parquet_url", "rows", "snapshot_bytes", "snapshot_path", "snapshot_sha256",
    "status", "target", "version"))
_ARCHIVE = "Git object 0b99589:docs/publication/2026-09-28/evidence/source/"
_RETIRED = "docs/government-academic-separation-plan-2026-10-01.md"
_RESEARCH_WARNING = (
    "Historical public research data may already have been used in training and attack development; "
    "reuse does not create a fresh holdout, establish person-level disjointness, or authorize production."
)
_BUNDLED_WARNING = (
    "Bundled by scikit-learn and exercised by the government educational console; this is not an "
    "additional academic study. Upstream terms still require review; the catalog does not infer a license."
)
_UNAVAILABLE_WARNING = (
    "No loader is provided by this adapter. Historical records establish use, not current local "
    "availability, complete source custody, model compatibility, or release approval."
)


class CatalogError(ValueError):
    """The retained catalog registration could not be safely validated."""


def _entry(identifier, label, kind, task, modality, sector, notes, references, *, corpus=None, loader_id=None):
    return {"id": identifier, "label": label, "kind": kind, "task": task, "corpus": corpus,
            "loader_id": loader_id, "modality": modality, "sector": sector,
            "provenance_notes": list(notes), "research_references": list(references)}


def _static_entries():
    # Construct fresh containers each time; caller edits cannot change later catalogs.
    entries = []
    prepared = (
        ("acs", "ACS public-use microdata", "population and socioeconomic statistics", (
            "The completed ACS study reports 120 target fits across 2009/2014/2019/2024 endpoint "
            "cohorts: 62,469,664 original rows and 24,454,622 eligible adult-householder rows. "
            "These counts are not a claim that every original row was trained on.",
            "Earlier ACS experiments used 2020-2024 national public-use person records; public "
            "household keys do not prove unique citizens across years. ACS is distinct from Adult Census Income.",
            "The retained records describe public Census sources; no agency-data authority or legal clearance is inferred.",
        ), (
            _ARCHIVE + "academic/full-corpus-study-20260921/results-v1/REPORT.md",
            _ARCHIVE + "reproduction/acs-attribute-dp-20260921/report-v1/REPORT.md",
            "docs/advisory/technical-report-2026-10-01.md",
        )),
        ("bts", "BTS public flight records", "aviation and transport", (
            "Completed multi-corpus history experiments report 147 target fits for BTS; a later "
            "matched stress study identifies BTS 2025 and a 50,000-record cohort.",
            "Retained aggregate reports do not establish the complete upstream download or licensing chain.",
        ), ()),
        ("hmda", "HMDA public mortgage records", "housing and financial services", (
            "Completed multi-corpus history experiments report 147 target fits for HMDA; a later "
            "matched stress study identifies HMDA 2024 and a 50,000-record cohort.",
            "Public mortgage data and a local byte receipt do not establish permission for confidential agency records.",
        ), ()),
        ("tlc", "NYC TLC public trip records", "urban transport", (
            "Completed multi-corpus history experiments report 147 target fits for TLC; a later "
            "matched stress study identifies January-July 2026 trips and a 50,000-record cohort.",
            "Retained aggregate reports do not establish the complete upstream download or licensing chain.",
        ), ()),
    )
    for corpus, label, sector, notes, references in prepared:
        if corpus != "acs":
            references = (
                _ARCHIVE + "academic/multicorpus-export-20260925/history-audit-v1/REPORT.md",
                _ARCHIVE + "academic/information-acquisition-next-20260925/matched-audit-v1/REPORT.md",
            )
        entries.append(_entry(corpus, label, "research_prepared", "classification", "tabular", sector,
            (*notes, "The allowlisted loader uses only the prepared public covariates and binary target; "
             "availability and exact source-byte verification occur separately at load time.", _RESEARCH_WARNING),
            (*references, _RETIRED), corpus=corpus, loader_id="research_prepared_v1"))

    bundled = (
        ("sklearn-breast-cancer", "Scikit-learn breast cancer diagnostic", "classification", "tabular",
         "health research", "569 records, 30 features, two diagnostic classes. OpenML wdbc shares an underlying "
         "dataset family but is a separately registered representation; byte identity is not assumed."),
        ("sklearn-wine", "Scikit-learn wine", "classification", "tabular", "agriculture and chemistry",
         "178 records, 13 features, three classes."),
        ("sklearn-digits", "Scikit-learn digits", "classification", "image-derived numeric pixels",
         "handwriting recognition", "1,797 8-by-8 digit images, 64 numeric pixels and ten classes. "
         "This is distinct from MNIST and the larger registered OpenML optdigits representation."),
        ("sklearn-diabetes", "Scikit-learn diabetes regression", "regression", "tabular", "health research",
         "442 records and ten features with a continuous progression target. This is distinct from "
         "the 768-record binary OpenML diabetes/Pima registration."),
    )
    for identifier, label, task, modality, sector, note in bundled:
        entries.append(_entry(identifier, label, "bundled", task, modality, sector, (note, _BUNDLED_WARNING),
            ("src/model_release_assurance/public_models.py",
             "reproduction/local-framework-validation/validation-report.md"), loader_id=identifier))

    finite_refs = ("reproduction/model-backed-finite-channel/config.json",
        "reproduction/model-backed-finite-channel/results/v3/manifest.json", "scripts/run_public_privacy_audit.py")
    historical = (
        ("uci-adult", "Adult Census Income (OpenML 1590 version 2)", "tabular", "socioeconomic statistics", (
            "Completed model-backed finite-channel experiments used Adult with XGBoost. The public audit "
            "script records OpenML 1590 and a CC BY 4.0 declaration; this is not a new legal determination.",
            "Adult and the separate ACS prepared corpus are different datasets. The OpenML registration "
            "below represents the same Adult family and is not another independent research corpus.",
        ), finite_refs),
        ("uci-covertype", "UCI Covertype", "tabular", "forestry and land cover", (
            "Completed historical tree experiments used UCI Covertype: 581,012 records, 54 features, "
            "seven classes; nested training subsets of 50,000/200,000/400,000 records were reported.",
            "The retained report declares CC BY 4.0, DOI 10.24432/C50K5N and source SHA256 "
            "614360d0257557dd1792834a85a1cdebfadc3c4f30b011d56afee7ffb5b15771. "
            "The catalog does not revalidate upstream custody or license terms.",
        ), (_ARCHIVE + "output/public-data-validation-20260906/tree/report.json", _RETIRED)),
        ("mnist", "MNIST (OpenML 554 version 1)", "images", "handwriting recognition", (
            "Completed model-backed finite-channel experiments used MNIST with a CNN. The public "
            "audit script records OpenML 554 and a CC BY-SA 3.0 declaration; rights are not independently cleared.",
            "MNIST is distinct from sklearn digits. Its OpenML registration below is not an additional corpus.",
        ), finite_refs),
        ("eurosat-rgb", "EuroSAT RGB", "satellite images", "land cover and remote sensing", (
            "Completed AlexNet/DenseNet121 training-hook runs used 27,000 real Sentinel-2 RGB patches "
            "(21,600 train and 5,400 test, ten classes); a later historical scalability run also completed.",
            "Configuration declares MIT and DOI 10.5281/zenodo.7711810, but retains MANUAL_REVIEW_REQUIRED "
            "and Sentinel terms review. Hash-stratified splitting does not establish spatial independence.",
        ), ("reproduction/vision-training-hook/config.json", "docs/real-data-training-hook-audit-2026-09-02.md",
            _ARCHIVE + "output/public-data-validation-20260906/vision/results/report.json", _RETIRED)),
        ("wildchat-4.8m", "WildChat-4.8M selected shard", "conversation text", "human-assistant dialogue", (
            "Completed language-model training-hook runs used one pinned shard with 37,208 rows, "
            "15,730 eligible unique English first-turn pairs, and 9,216 selected pairs (8,192 train/1,024 holdout); "
            "the full 86-shard corpus was not used.",
            "Pinned allenai/WildChat-4.8M revision c827c6df8fcf008219ffaffa4d1dd77491099367; "
            "the configuration declares ODC-By 1.0 and content_rights_cleared=false. The raw shard retains "
            "excluded metadata; filtering does not establish deidentification, safe redistribution or retention approval.",
        ), ("reproduction/llm-training-hook/config.json", "docs/real-data-training-hook-audit-2026-09-02.md")),
        ("dolly-15k", "Dolly 15k historical instruction corpus", "instruction text", "instruction following", (
            "The completed historical Dolly/GPT-2/Qwen scaling report records 15,011 source rows, "
            "14,996 distinct texts and 9,216 selected rows, with 1,024/4,096/8,192 training sizes.",
            "The inspected retained summary does not establish an exact upstream dataset revision or "
            "license grant; those must be recovered and reviewed before any new ingestion.",
        ), (_ARCHIVE + "output/public-data-validation-20260906/llm/scaling-run-v2/report.json", _RETIRED)),
        ("20newsgroups", "20 Newsgroups selected topics", "text", "topic classification", (
            "Completed model-backed finite-channel experiments used comp.graphics, rec.sport.baseball, "
            "sci.space and talk.politics.misc after removing headers, footers and quotes, with a compact "
            "transformer classifier proxy; this was not a pretrained language-model study.",
            "The public audit script points to the 20 Newsgroups source and records no standardized "
            "license declaration. Text availability does not establish content rights.",
        ), finite_refs),
    )
    for identifier, label, modality, sector, notes, references in historical:
        entries.append(_entry(identifier, label, "historical_unavailable", "unsupported", modality, sector,
                              (*notes, _UNAVAILABLE_WARNING), references))
    return entries


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise CatalogError("Duplicate OpenML manifest field")
        value[key] = item
    return value


def _constant(_):
    raise CatalogError("Nonfinite OpenML manifest number")


def _text(value, maximum=256):
    return type(value) is str and 1 <= len(value) <= maximum and all(ord(c) >= 32 for c in value)


def _integer(value, minimum=1, maximum=1000000000):
    return type(value) is int and minimum <= value <= maximum


def _digest(value, pattern=_SHA256):
    return type(value) is str and pattern.fullmatch(value) is not None


def _validate_manifest(manifest):
    if type(manifest) is not dict or set(manifest) != _TOP_FIELDS:
        raise CatalogError("Unexpected OpenML manifest fields")
    if (manifest["manifest_version"] != "1.0" or type(manifest["study_id"]) is not int
            or manifest["study_id"] != 99 or manifest["study_alias"] != "OpenML-CC18"
            or manifest["config_path"] != "reproduction/openml/config.json"
            or manifest["study_url"] != "https://www.openml.org/api/v1/json/study/99"
            or not _digest(manifest["config_sha256"]) or not _digest(manifest["study_sha256"])):
        raise CatalogError("OpenML suite identity differs from the retained registration")
    for field, count in (("configured_dataset_count", 72), ("successful_dataset_count", 72),
                         ("failed_dataset_count", 0)):
        if type(manifest[field]) is not int or manifest[field] != count:
            raise CatalogError("OpenML registration count differs from the retained suite")
    datasets = manifest["datasets"]
    if type(datasets) is not list or len(datasets) != 72 or manifest["failures"] != []:
        raise CatalogError("Incomplete OpenML registration list")
    seen = set()
    for item in datasets:
        if type(item) is not dict or set(item) != _DATASET_FIELDS:
            raise CatalogError("Unexpected OpenML dataset fields")
        identifier = item["dataset_id"]
        if not _integer(identifier) or identifier in seen:
            raise CatalogError("Invalid or duplicate OpenML dataset ID")
        seen.add(identifier)
        if (not _integer(item["version"], maximum=10000) or not _text(item["name"])
                or not _integer(item["rows"]) or not _integer(item["classes"], 2, 10000)
                or not _integer(item["features"], maximum=10000)
                or not _integer(item["snapshot_bytes"], maximum=512 * 1024 * 1024)
                or not _integer(item["missing_feature_values"], 0, 100000000000)
                or not _digest(item["snapshot_sha256"]) or not _digest(item["openml_md5_checksum"], _MD5)
                or item["snapshot_path"] != f"reproduction/openml/raw/openml-{identifier}.parquet"
                or not _text(item["target"]) or item["status"] != "active"
                or not _text(item["file_id"]) or not item["file_id"].isdigit()
                or not _text(item["openml_url"], 1024) or not _text(item["parquet_url"], 1024)):
            raise CatalogError("Invalid OpenML dataset identity or byte receipt")
        names, dtypes, counts = item["feature_names"], item["feature_dtypes"], item["class_counts"]
        if (type(names) is not list or len(names) != item["features"]
                or not all(_text(name) for name in names) or len(set(names)) != len(names)
                or type(dtypes) is not dict or set(dtypes) != set(names)
                or not all(dtype in {"category", "float64", "int64", "object", "uint8"}
                           for dtype in dtypes.values())
                or type(counts) is not dict or len(counts) != item["classes"]
                or not all(_text(name) and _integer(count) for name, count in counts.items())
                or sum(counts.values()) != item["rows"]):
            raise CatalogError("Inconsistent OpenML feature or class metadata")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    if hashlib.sha256(canonical).hexdigest() != _OPENML_SHA256:
        raise CatalogError("OpenML registration metadata differs from its reviewed semantic digest")
    return datasets


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directories(path):
    stamps = []
    for current in (*reversed(path.parents), path):
        info = current.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            raise CatalogError("Catalog directories must be ordinary local directories")
        stamps.append((current, info.st_dev, info.st_ino))
    return tuple(stamps)


def _stamp(info):
    if _unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CatalogError("Catalog manifest must be an ordinary single-link file")
    # Windows Python 3.12 lstat/fstat disagree on ctime semantics.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _load_openml(root):
    try:
        supplied = Path(root)
        if ".." in supplied.parts or str(supplied).startswith(("//", "\\\\")):
            raise CatalogError("Catalog root must be a local path without traversal")
        path = supplied.absolute() / OPENML_MANIFEST
        directories = _directories(path.parent)
        stamp = _stamp(path.lstat())
        if not 1 <= stamp[2] <= MAX_MANIFEST_BYTES:
            raise CatalogError("OpenML manifest exceeds its size bound")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            if _stamp(os.fstat(stream.fileno())) != stamp:
                raise CatalogError("OpenML manifest changed while opening")
            content = stream.read(MAX_MANIFEST_BYTES + 1)
            if len(content) != stamp[2] or _stamp(os.fstat(stream.fileno())) != stamp:
                raise CatalogError("OpenML manifest changed while reading")
        if _stamp(path.lstat()) != stamp or _directories(path.parent) != directories:
            raise CatalogError("OpenML manifest path changed while reading")
        return _validate_manifest(json.loads(content.decode("utf-8"), object_pairs_hook=_pairs,
                                             parse_constant=_constant))
    except CatalogError:
        raise
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        raise CatalogError("OpenML manifest is missing, malformed or unsafe") from None


def catalog_entries(root: Path) -> list[dict]:
    """Return reviewed provenance, without probing data availability or loading arrays.

    The government repository root is explicit. A missing or changed OpenML
    manifest is an error, rather than a silently shortened registration catalog.
    """
    registered = _load_openml(root)
    entries = _static_entries()
    image_origins = {28, 32, 554, 1501, 40923, 40927, 40979, 40996}
    for item in sorted(registered, key=lambda entry: entry["dataset_id"]):
        identifier, version = item["dataset_id"], item["version"]
        entries.append(_entry(f"openml-{identifier}-v{version}", f"OpenML {item['name']} (ID {identifier}, version {version})",
            "openml_registered", "unsupported", "image-derived feature table" if identifier in image_origins else "tabular feature representation",
            "cross-domain classification benchmark", (
                "registered_not_proven_all_trained: one of 72 OpenML-CC18 dataset registrations; "
                "metadata and planned subsets do not prove 72 completed model-training runs.",
                f"Registered shape: {item['rows']} rows, {item['features']} features, {item['classes']} classes; "
                f"snapshot SHA256 {item['snapshot_sha256']}. The snapshot itself is not opened or validated by this catalog.",
                "The retained manifest contains no dataset license field. Verify each upstream dataset's "
                "terms and custody before ingestion; catalog presence grants no permission or adapter support.",
            ), (OPENML_MANIFEST.as_posix(), "reproduction/README.md")))
    return entries
