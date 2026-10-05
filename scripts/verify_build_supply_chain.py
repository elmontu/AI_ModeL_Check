#!/usr/bin/env python3
"""Verify locked public-fixture wheels and optional public PyPI observations.

This tool neither installs wheels nor authorizes deployment. Network access is
explicit through --download and/or --scan-pypi. Every run uses a new ignored
.local directory and retains its evidence, including unsuccessful runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).absolute().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
_BASELINE_SPEC = importlib.util.spec_from_file_location("mra_supply_chain_baseline", ROOT / "scripts/verify_build_baseline.py")
_BASELINE = importlib.util.module_from_spec(_BASELINE_SPEC)
_BASELINE_SPEC.loader.exec_module(_BASELINE)

from model_release_assurance.production_build import artifacts, evidence

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_REQUIREMENTS_BYTES = 128 * 1024
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
FLAGS = {"fixture_only": True, "production_authorized": False, "deployable": False,
         "source_verified": False, "license_approved": False}
LIMITATIONS = [
    "The public-fixture lock and locally supplied inputs are trusted, not independently authenticated.",
    "PyPI JSON covers reported advisories for listed distributions; it is not a code, malware or container scan.",
    "Wheel tags and dependency metadata do not prove runtime compatibility or safe installation.",
    "Declared licenses require agency review; source/build binding, publisher identity and production admission are not established.",
]


class SupplyChainError(ValueError):
    pass


def _sha(content):
    return hashlib.sha256(content).hexdigest()


def _input_path(root, value):
    value = Path(value)
    if ".." in value.parts:
        raise SupplyChainError("Input traversal is refused")
    path = (value if value.is_absolute() else root / value).absolute()
    try:
        path.relative_to(root)
    except ValueError:
        raise SupplyChainError("Inputs must be inside the repository") from None
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SupplyChainError("Input links or reparse points are refused")
    return path


def _read_input(root, value, maximum):
    path = _input_path(root, value)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise SupplyChainError("Input must be a bounded ordinary file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise SupplyChainError("Input identity changed while opening")
        content = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    _input_path(root, path)
    final = path.lstat()
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_nlink)
    if signature(before) != signature(opened) or signature(opened) != signature(after) or signature(after) != signature(final) or len(content) != after.st_size:
        raise SupplyChainError("Input changed during read")
    return path, content


def validate_requirements(content, manifest):
    """Require one sorted, exact hash-pinned line for every locked artifact."""
    if type(content) is not bytes or not 0 < len(content) <= MAX_REQUIREMENTS_BYTES:
        raise SupplyChainError("Requirements input exceeds its bound")
    try:
        lines = [line.strip() for line in content.decode("utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    except UnicodeError:
        raise SupplyChainError("Requirements must be UTF-8") from None
    expected = [f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}"
                for item in sorted(manifest["artifacts"], key=lambda item: item["name"])]
    if lines != expected:
        raise SupplyChainError("Requirements differ from the complete sorted wheel lock")


def _public_url(url, host):
    if type(url) is not str or not 1 <= len(url) <= 4096 or any(ord(char) <= 32 or ord(char) >= 127 for char in url):
        raise SupplyChainError("Invalid public artifact URL")
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == "https" and parsed.netloc == host and parsed.hostname == host
                 and parsed.username is None and parsed.password is None and parsed.port is None
                 and parsed.path.startswith("/") and not parsed.query and not parsed.fragment
                 and "\\" not in url)
    except ValueError:
        valid = False
    if not valid:
        raise SupplyChainError("Untrusted public artifact URL")
    return url


class _SameHostRedirect(HTTPRedirectHandler):
    def __init__(self, host):
        self.host = host

    def redirect_request(self, request, fp, code, message, headers, newurl):
        _public_url(newurl, self.host)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch_public(url, *, maximum, host):
    """Bounded HTTPS GET; every redirect and final response stays on one host."""
    _public_url(url, host)
    request = Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "mra-public-fixture-lock/1"})
    opener = build_opener(_SameHostRedirect(host))
    with opener.open(request, timeout=30) as response:
        _public_url(response.geturl(), host)
        if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
            raise SupplyChainError("Unsupported public artifact response")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or len(length) > 12 or int(length) > maximum):
            raise SupplyChainError("Public response exceeds its bound")
        content = response.read(maximum + 1)
        if not content or len(content) > maximum or (length is not None and len(content) != int(length)):
            raise SupplyChainError("Public response has an invalid size")
        return content


def _metadata_url(item):
    return "https://pypi.org/pypi/" + quote(item["name"], safe="") + "/" + quote(item["version"], safe="") + "/json"


def _download_url(item, body):
    parsed = evidence.strict_json_bytes(body, maximum=evidence.MAX_RESPONSE_BYTES)
    entries = parsed.get("urls")
    if type(entries) is not list or len(entries) > 4096:
        raise SupplyChainError("Missing bounded PyPI file inventory")
    matches = [entry for entry in entries if type(entry) is dict and entry.get("filename") == item["filename"]]
    if len(matches) != 1:
        raise SupplyChainError("Expected wheel is absent or ambiguous on PyPI")
    entry = matches[0]
    if (entry.get("packagetype") != "bdist_wheel" or entry.get("yanked") is not False
            or type(entry.get("size")) is not int or entry["size"] != item["size_bytes"]
            or type(entry.get("digests")) is not dict or entry["digests"].get("sha256") != item["sha256"]):
        raise SupplyChainError("PyPI wheel identity differs from the lock or is yanked")
    return _public_url(entry.get("url"), "files.pythonhosted.org")


def _error_observation(item, now):
    return {"name": item["name"], "version": item["version"], "fetched_at": now,
            "source": "pypi-json", "status": "error", "error": "fetch_failed"}


def _save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def run_supply_chain(*, root, manifest_path, output, requirements_path=None, wheelhouse=None,
                     download=False, scan_pypi=False, fetcher=None, now=None):
    """Return result.json data; output refusal raises before any writes occur."""
    root = Path(root).absolute()
    destination = _BASELINE.prepare_output(root, output)
    fetcher = fetcher or fetch_public
    now = int(time.time()) if now is None else now
    observations, inputs, inventory = [], {}, None
    unavailable = {"status": "unavailable", **FLAGS}
    report, sbom = dict(unavailable), dict(unavailable)
    result = {"schema": "mra-supply-chain-run/v1", "status": "failed", "evaluated_at": now,
              "download_requested": download, "scan_requested": scan_pypi, "errors": [],
              "limitations": LIMITATIONS, **FLAGS}
    try:
        if type(now) is not int or not 0 <= now <= 2**53 - 1:
            raise SupplyChainError("Invalid evaluation time")
        if type(download) is not bool or type(scan_pypi) is not bool or download == (wheelhouse is not None):
            raise SupplyChainError("Choose exactly one wheelhouse or download")
        manifest_file, raw_manifest = _read_input(root, manifest_path, MAX_INPUT_BYTES)
        manifest = artifacts.parse_manifest_json(raw_manifest)
        inventory = sorted(manifest["artifacts"], key=lambda item: item["name"])
        requirement_file, raw_requirements = _read_input(
            root, requirements_path or manifest_file.with_suffix(".requirements.txt"), MAX_REQUIREMENTS_BYTES)
        validate_requirements(raw_requirements, manifest)
        inputs = {"manifest": {"path": manifest_file.relative_to(root).as_posix(), "sha256": _sha(raw_manifest)},
                  "requirements": {"path": requirement_file.relative_to(root).as_posix(), "sha256": _sha(raw_requirements)}}
        if download:
            if sum(item["size_bytes"] for item in inventory) > MAX_DOWNLOAD_BYTES:
                raise SupplyChainError("Locked downloads exceed the aggregate bound")
            house = destination / "wheelhouse"
            house.mkdir()
        else:
            house = _input_path(root, wheelhouse)
        # A metadata body is fetched once per exact version and reused for the
        # advisory observation. No scan means no observations are claimed.
        if download or scan_pypi:
            response_bytes = 0
            for item in inventory:
                try:
                    body = fetcher(_metadata_url(item), maximum=evidence.MAX_RESPONSE_BYTES, host="pypi.org")
                    observation = evidence.parse_pypi_observation(item["name"], item["version"], body, fetched_at=now)
                    response_bytes += len(body)
                    if response_bytes * 4 // 3 + len(inventory) * 4096 > evidence.MAX_OBSERVATION_BYTES:
                        raise SupplyChainError("Aggregate observation evidence exceeds its bound")
                except Exception:
                    if scan_pypi:
                        observations.append(_error_observation(item, now))
                    if download:
                        raise SupplyChainError("Required public version metadata could not be verified") from None
                    continue
                if scan_pypi:
                    observations.append(observation)
                if download:
                    url = _download_url(item, body)
                    content = fetcher(url, maximum=item["size_bytes"], host="files.pythonhosted.org")
                    if type(content) is not bytes or len(content) != item["size_bytes"] or _sha(content) != item["sha256"]:
                        raise SupplyChainError("Downloaded wheel bytes differ from the lock")
                    with (house / item["filename"]).open("xb") as stream:
                        stream.write(content)
        report = artifacts.verify_wheel_bundle(manifest, house)
        sbom = artifacts.build_cyclonedx_sbom(report)
        for label, maximum in (("manifest", MAX_INPUT_BYTES), ("requirements", MAX_REQUIREMENTS_BYTES)):
            _, final = _read_input(root, inputs[label]["path"], maximum)
            if _sha(final) != inputs[label]["sha256"]:
                raise SupplyChainError("Input changed during verification")
    except (SupplyChainError, artifacts.ArtifactError, evidence.BuildEvidenceError) as exc:
        result["errors"].append(str(exc))
    except Exception:
        result["errors"].append("Input, download or verification operation failed")
    try:
        advisories = evidence.evaluate_advisories(inventory, observations, now=now) if inventory else dict(unavailable)
    except evidence.BuildEvidenceError:
        advisories = dict(unavailable)
        result["errors"].append("Advisory evidence exceeded bounds or was invalid")
    verified = report.get("status") == "verified" and not result["errors"]
    clean = advisories.get("coverage_complete") is True and advisories.get("advisory_clear") is True
    result.update({"status": "passed" if verified and clean else "failed", "wheel_bundle_verified": verified,
                   "advisory_clear": clean, "inputs": inputs,
                   "inventory_sha256": report.get("inventory_sha256"),
                   "advisory_report_sha256": evidence.canonical_sha256(advisories)})
    if not scan_pypi:
        result["errors"].append("Advisory scan was not requested; coverage is incomplete")
    elif not clean:
        result["errors"].append("Advisory coverage is incomplete or reported vulnerabilities remain")
    licenses = {"status": "pending_agency_review", "license_approved": False, **FLAGS,
                "components": [{key: item[key] for key in ("name", "version", "license_status", "declared_license",
                                "license_expression", "license_files", "missing_declared_license_files")}
                               for item in report.get("components", [])]}
    for name, document in (("inventory.json", report), ("sbom.cdx.json", sbom), ("observations.json", observations),
                           ("advisories.json", advisories), ("license-review.json", licenses), ("result.json", result)):
        _save(destination / name, document)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--requirements")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--wheelhouse")
    source.add_argument("--download", action="store_true")
    parser.add_argument("--scan-pypi", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_supply_chain(root=ROOT, manifest_path=args.manifest, requirements_path=args.requirements,
                                  wheelhouse=args.wheelhouse, download=args.download, scan_pypi=args.scan_pypi,
                                  output=args.output)
    except (_BASELINE.BaselineError, OSError):
        print(json.dumps({"status": "output_refused", **FLAGS}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
