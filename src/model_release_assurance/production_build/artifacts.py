"""Read-only wheel-lock verification and declared-license CycloneDX evidence.

No wheel is installed, imported, executed or extracted. Compatibility is an
explicit target-tag/metadata calculation, not a Linux or Windows runtime test.
Hashes bind supplied bytes; they do not authenticate a publisher or approve a
license. This optional utility requires packaging>=26.3,<27.
"""
from __future__ import annotations

from collections import deque
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import quote
import zipfile

from packaging.markers import Variable
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags, parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

MAX_WHEELS = 128
MAX_WHEEL_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 20000
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_LICENSE_BYTES = 2 * 1024 * 1024
SUPPORTED_METADATA = frozenset({"1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"})
SUPPORTED_MARKERS = frozenset({"implementation_name", "implementation_version", "os_name", "platform_machine",
    "platform_python_implementation", "platform_system", "python_full_version", "python_version", "sys_platform", "extra"})


class ArtifactError(ValueError):
    pass


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def _fail(reason):
    raise ArtifactError(reason)


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail("Invalid exact fields: " + label)


def _text(value, maximum, label):
    if type(value) is not str or not 1 <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        _fail("Invalid bounded text: " + label)
    return value


def _marker_variables(node):
    if isinstance(node, Variable):
        yield node.value
    elif isinstance(node, (list, tuple)):
        for child in node:
            yield from _marker_variables(child)


def _requirement(value, *, pinned=False):
    _text(value, 1024, "requirement")
    try:
        result = Requirement(value)
        if result.url:
            _fail("Direct URL requirements are unsupported")
        if result.marker:
            # packaging26's parsed AST identifies variables, not quoted literals.
            variables = set(_marker_variables(result.marker._markers))
            if not variables <= SUPPORTED_MARKERS:
                _fail("Requirement marker needs an unspecified target property")
        if pinned:
            specs = list(result.specifier)
            if len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
                _fail("Root requirements must pin one exact version")
            Version(specs[0].version)
        if len(result.extras) > 32:
            _fail("Too many requested extras")
        return result
    except (ValueError, RecursionError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("Invalid requirement") from None


def validate_manifest(manifest):
    _fields(manifest, ("schema", "environment", "target", "roots", "artifacts"), "manifest")
    if manifest["schema"] != "mra-wheel-lock/v1" or manifest["environment"] != "public_fixture":
        _fail("Unsupported wheel-lock schema or environment")
    target = manifest["target"]
    _fields(target, ("python_version", "python_full_version", "implementation", "platform"), "target")
    if (target["python_version"] != "3.12" or target["python_full_version"] != "3.12.14"
            or target["implementation"] != "cpython" or target["platform"] not in ("win_amd64", "manylinux_2_28_x86_64")):
        _fail("Unsupported explicit target")
    if type(manifest["roots"]) is not list or not 1 <= len(manifest["roots"]) <= 64:
        _fail("Invalid root requirements")
    roots = [_requirement(value, pinned=True) for value in manifest["roots"]]
    if len({canonicalize_name(item.name) for item in roots}) != len(roots):
        _fail("Duplicate root distributions")
    if type(manifest["artifacts"]) is not list or not 1 <= len(manifest["artifacts"]) <= MAX_WHEELS:
        _fail("Invalid wheel artifact count")
    names, filenames = set(), set()
    for artifact in manifest["artifacts"]:
        _fields(artifact, ("name", "version", "filename", "sha256", "size_bytes"), "artifact")
        name = _text(artifact["name"], 128, "name")
        version = _text(artifact["version"], 128, "version")
        filename = _text(artifact["filename"], 240, "filename")
        try:
            if canonicalize_name(name, validate=True) != name or str(Version(version)) != version:
                _fail("Name/version must be normalized")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*\.whl", filename):
                _fail("Wheel filename must be a plain basename")
            parsed_name, parsed_version, _, tags = parse_wheel_filename(filename)
            if parsed_name != name or parsed_version != Version(version) or len(tags) > 256:
                _fail("Wheel filename identity differs from manifest")
        except ValueError as error:
            if isinstance(error, ArtifactError):
                raise
            raise ArtifactError("Invalid wheel identity") from None
        if type(artifact["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
            _fail("Invalid artifact digest")
        if type(artifact["size_bytes"]) is not int or not 1 <= artifact["size_bytes"] <= MAX_WHEEL_BYTES:
            _fail("Invalid wheel byte bound")
        if name in names or filename.casefold() in filenames:
            _fail("Duplicate artifact name or filename")
        names.add(name)
        filenames.add(filename.casefold())
    return json.loads(json.dumps(manifest, allow_nan=False))


def _pairs(pairs):
    value = {}
    for name, item in pairs:
        if name in value:
            _fail("Duplicate manifest JSON key")
        value[name] = item
    return value


def _number(value):
    if len(value) > 16:
        _fail("Oversized manifest integer")
    return int(value)


def _nonfinite(value):
    _fail("Non-finite manifest value")


def parse_manifest_json(content):
    if type(content) not in (bytes, str) or len(content) > 2 * 1024 * 1024:
        _fail("Manifest exceeds input bound")
    try:
        value = json.loads(content, object_pairs_hook=_pairs, parse_int=_number, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("Invalid manifest JSON") from None
    return validate_manifest(value)


def marker_environment(target):
    windows = target["platform"] == "win_amd64"
    return {"implementation_name": "cpython", "implementation_version": target["python_full_version"],
            "os_name": "nt" if windows else "posix", "platform_machine": "AMD64" if windows else "x86_64",
            "platform_python_implementation": "CPython", "platform_release": "", "platform_version": "",
            "platform_system": "Windows" if windows else "Linux", "python_full_version": target["python_full_version"],
            "python_version": target["python_version"], "sys_platform": "win32" if windows else "linux", "extra": ""}


def _target_tags(target):
    if target["platform"] == "win_amd64":
        platforms = ["win_amd64"]
    else:
        platforms = ["manylinux_2_" + str(minor) + "_x86_64" for minor in range(28, 4, -1)]
        platforms += ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
    return set(cpython_tags((3, 12), abis=["cp312"], platforms=platforms)) | set(compatible_tags((3, 12), interpreter="cp312", platforms=platforms))


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _check_directory(path):
    for current in (*reversed(path.parents), path):
        info = current.lstat()
        if _link(info) or not stat.S_ISDIR(info.st_mode):
            _fail("Wheelhouse directory is not an ordinary directory")


def _read_file(path, expected_size):
    before = path.lstat()
    if _link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != expected_size:
        _fail("Wheel file identity or size is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if _link(opened) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            _fail("Wheel file changed while opening")
        content = stream.read(expected_size + 1)
        after = os.fstat(stream.fileno())
    final = path.lstat()
    if (_link(final) or final.st_nlink != 1 or after.st_nlink != 1
            or (final.st_dev, final.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or (after.st_size, after.st_mtime_ns) != (final.st_size, final.st_mtime_ns) or len(content) != expected_size):
        _fail("Wheel file changed during read")
    return content


def _member_name(name):
    stripped = name[:-1] if name.endswith("/") else name
    if (not stripped or "\\" in stripped or ":" in stripped or any(ord(char) < 32 or ord(char) == 127 for char in stripped) or PurePosixPath(stripped).is_absolute()
            or any(part in ("", ".", "..") for part in stripped.split("/"))):
        _fail("Unsafe wheel ZIP path")
    return stripped


def _zip_inventory(archive, windows):
    infos = archive.infolist()
    if not 1 <= len(infos) <= MAX_MEMBERS:
        _fail("Wheel ZIP member count exceeds bound")
    seen, total = set(), 0
    for info in infos:
        if info.orig_filename != info.filename:
            _fail("Noncanonical ZIP member name")
        name = _member_name(info.filename)
        if windows:
            devices = {"CON", "PRN", "AUX", "NUL"} | {prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"}
            for part in name.split("/"):
                if (part.endswith((".", " ")) or part.split(".", 1)[0].strip().upper() in devices
                        or any(char in '<>"|?*' for char in part)):
                    _fail("Win32-ambiguous ZIP member name")
        unique = name.casefold() if windows else name
        mode = stat.S_IFMT(info.external_attr >> 16)
        if unique in seen or info.flag_bits & 1 or mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            _fail("Duplicate, encrypted or linked ZIP member")
        if info.is_dir() != (mode == stat.S_IFDIR) and mode != 0:
            _fail("ZIP member mode/path mismatch")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            _fail("Unsupported ZIP compression")
        if info.file_size > MAX_MEMBER_BYTES or info.file_size > max(1024 * 1024, info.compress_size * 200):
            _fail("Wheel ZIP expansion exceeds bound")
        total += info.file_size
        if total > MAX_EXPANDED_BYTES:
            _fail("Wheel total expanded size exceeds bound")
        seen.add(unique)
    file_paths = {info.filename.casefold() if windows else info.filename for info in infos if not info.is_dir()}
    for info in infos:
        path = info.filename.casefold() if windows else info.filename
        parts = path.rstrip("/").split("/")
        if any("/".join(parts[:index]) in file_paths for index in range(1, len(parts))):
            _fail("ZIP file/directory prefix collision")
    return {info.filename: info for info in infos if not info.is_dir()}


def _member_bytes(archive, info, limit):
    if info.file_size > limit:
        _fail("Wheel metadata/license exceeds byte bound")
    with archive.open(info) as stream:
        content = stream.read(limit + 1)
    if len(content) != info.file_size or len(content) > limit:
        _fail("Wheel metadata/license expanded size mismatch")
    return content


def _header(message, name, *, required=False):
    values = message.get_all(name, [])
    if len(values) > 1 or (required and len(values) != 1):
        _fail("Missing or duplicate wheel metadata field: " + name)
    return str(values[0]).strip() if values else None


def _parse_email(content):
    message = BytesParser(policy=policy.default).parsebytes(content)
    if message.defects:
        _fail("Malformed wheel metadata headers")
    return message


def _inspect_wheel(content, artifact, target):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = _zip_inventory(archive, target["platform"] == "win_amd64")
            dist_infos = {name.split("/")[0] for name in files if name.split("/")[0].endswith(".dist-info")}
            if len(dist_infos) != 1:
                _fail("Wheel must contain exactly one dist-info directory")
            dist_info = next(iter(dist_infos))
            distribution, version = dist_info[:-10].rsplit("-", 1)
            if canonicalize_name(distribution) != artifact["name"] or Version(version) != Version(artifact["version"]):
                _fail("Wheel dist-info identity differs from manifest")
            metadata = _parse_email(_member_bytes(archive, files[dist_info + "/METADATA"], MAX_METADATA_BYTES))
            if _header(metadata, "Metadata-Version", required=True) not in SUPPORTED_METADATA:
                _fail("Unsupported core metadata version")
            if (canonicalize_name(_header(metadata, "Name", required=True), validate=True) != artifact["name"]
                    or Version(_header(metadata, "Version", required=True)) != Version(artifact["version"])):
                _fail("Wheel METADATA identity differs from manifest")
            python_spec = _header(metadata, "Requires-Python")
            if python_spec and not SpecifierSet(python_spec).contains(target["python_full_version"], prereleases=True):
                _fail("Wheel Requires-Python excludes target")
            wheel = _parse_email(_member_bytes(archive, files[dist_info + "/WHEEL"], 65536))
            if _header(wheel, "Wheel-Version", required=True) != "1.0":
                _fail("Unsupported WHEEL version")
            if _header(wheel, "Root-Is-Purelib", required=True) not in ("true", "false"):
                _fail("Invalid WHEEL purelib declaration")
            declared_tags = wheel.get_all("Tag", [])
            if not 1 <= len(declared_tags) <= 256:
                _fail("Missing or excessive WHEEL tags")
            wheel_tags = set()
            for tag in declared_tags:
                wheel_tags.update(parse_tag(_text(str(tag), 256, "wheel tag"), limit=256))
            filename_tags = parse_wheel_filename(artifact["filename"])[-1]
            if wheel_tags != filename_tags or not wheel_tags & _target_tags(target):
                _fail("Wheel tags differ or do not match explicit target")
            requirements = [str(value) for value in metadata.get_all("Requires-Dist", [])]
            if len(requirements) > 512:
                _fail("Too many wheel requirements")
            for value in requirements:
                _requirement(value)
            extras = [canonicalize_name(_text(str(value), 128, "extra"), validate=True) for value in metadata.get_all("Provides-Extra", [])]
            if len(extras) > 64 or len(set(extras)) != len(extras):
                _fail("Invalid wheel extras")
            license_value = _header(metadata, "License")
            expression = _header(metadata, "License-Expression")
            license_names = [str(value) for value in metadata.get_all("License-File", [])]
            if len(license_names) > 128:
                _fail("Too many declared license files")
            selected_licenses, missing_licenses = set(), []
            for name in license_names:
                _member_name(name)
                possible = [dist_info + "/licenses/" + name, dist_info + "/" + name]
                found = [candidate for candidate in possible if candidate in files]
                selected_licenses.update(found)
                if not found:
                    missing_licenses.append(name)
            for name in files:
                if name.startswith(dist_info + "/licenses/") or (name.startswith(dist_info + "/") and name.rsplit("/", 1)[-1].upper().startswith(("LICENSE", "COPYING", "NOTICE"))):
                    selected_licenses.add(name)
            if len(selected_licenses) > 128:
                _fail("Too many license evidence files")
            evidence, total = [], 0
            for name in sorted(selected_licenses):
                data = _member_bytes(archive, files[name], MAX_LICENSE_BYTES)
                total += len(data)
                if total > 8 * 1024 * 1024:
                    _fail("License evidence exceeds total bound")
                evidence.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)})
            return {**artifact, "purl": "pkg:pypi/" + artifact["name"] + "@" + quote(artifact["version"], safe=""),
                    "requires_dist": requirements, "provides_extras": sorted(extras), "requires_python": python_spec,
                    "declared_license": license_value[:8192] if license_value else None,
                    "license_declaration_truncated": bool(license_value and len(license_value) > 8192),
                    "license_expression": expression[:4096] if expression else None,
                    "license_status": "declared_only" if expression or (license_value and license_value.upper() not in {"UNKNOWN", "NONE", "NOASSERTION", "N/A"}) else "unknown",
                    "license_files": evidence, "missing_declared_license_files": missing_licenses,
                    "metadata_sha256": hashlib.sha256(_member_bytes(archive, files[dist_info + "/METADATA"], MAX_METADATA_BYTES)).hexdigest()}
    except (KeyError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError("Invalid or unsupported wheel metadata") from None


def _active(requirement, environment, extras):
    return requirement.marker is None or any(requirement.marker.evaluate({**environment, "extra": extra}, context="metadata")
                                            for extra in {"", *extras})


def _closure(manifest, components):
    environment = marker_environment(manifest["target"])
    by_name = {component["name"]: component for component in components}
    requested, graph, pending = {}, {name: set() for name in by_name}, deque()
    active_roots = []
    def need(requirement, parent=None):
        name = canonicalize_name(requirement.name)
        if name not in by_name or not requirement.specifier.contains(by_name[name]["version"], prereleases=True):
            _fail("Missing or incompatible dependency: " + name)
        extras = {canonicalize_name(value) for value in requirement.extras}
        if not extras <= set(by_name[name]["provides_extras"]):
            _fail("Requested extra is not declared: " + name)
        if parent is not None:
            graph[parent].add(name)
        if name not in requested or not extras <= requested[name]:
            requested.setdefault(name, set()).update(extras)
            pending.append(name)
        return name
    for raw in manifest["roots"]:
        requirement = _requirement(raw, pinned=True)
        if _active(requirement, environment, set()):
            active_roots.append(need(requirement))
    while pending:
        parent = pending.popleft()
        for raw in by_name[parent]["requires_dist"]:
            requirement = _requirement(raw)
            if _active(requirement, environment, requested[parent]):
                need(requirement, parent)
    if set(requested) != set(by_name):
        _fail("Wheel bundle includes artifacts outside the complete selected dependency closure")
    return {name: sorted(graph[name]) for name in sorted(graph)}, sorted(active_roots), environment


def verify_wheel_bundle(manifest, wheelhouse):
    manifest = validate_manifest(manifest)
    wheelhouse = Path(wheelhouse).absolute()
    try:
        _check_directory(wheelhouse)
        identity = wheelhouse.stat().st_dev, wheelhouse.stat().st_ino
        expected = {item["filename"] for item in manifest["artifacts"]}
        if {path.name for path in wheelhouse.iterdir()} != expected:
            _fail("Wheelhouse must contain exactly the locked files and no extras")
        components = []
        for artifact in sorted(manifest["artifacts"], key=lambda item: item["name"]):
            content = _read_file(wheelhouse / artifact["filename"], artifact["size_bytes"])
            if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
                _fail("Wheel hash differs from lock: " + artifact["filename"])
            components.append(_inspect_wheel(content, artifact, manifest["target"]))
        _check_directory(wheelhouse)
        if identity != (wheelhouse.stat().st_dev, wheelhouse.stat().st_ino) or {path.name for path in wheelhouse.iterdir()} != expected:
            _fail("Wheelhouse changed during verification")
        graph, roots, environment = _closure(manifest, components)
    except OSError:
        raise ArtifactError("Wheel bundle is unavailable or unsafe") from None
    return {"schema": "mra-wheel-verification/v1", "status": "verified", "environment": "public_fixture",
            "target": manifest["target"], "manifest_sha256": canonical_sha256(manifest),
            "inventory_sha256": canonical_sha256(sorted(manifest["artifacts"], key=lambda item: item["name"])),
            "components": components, "dependency_graph": graph, "active_roots": roots, "marker_environment": environment,
            "production_approved": False, "license_approved": False,
            "limitations": ["Bytes and dependency closure are verified against supplied pins; publisher authenticity is not established.",
                            "Target tags and markers do not replace installation/runtime tests on the target operating system.",
                            "License fields and file hashes are declared evidence only; legal approval and unknown-license resolution remain pending."]}


def build_cyclonedx_sbom(report):
    if type(report) is not dict or report.get("status") != "verified" or report.get("schema") != "mra-wheel-verification/v1":
        _fail("A verified wheel report is required")
    components = []
    for component in report["components"]:
        license_name = component["license_expression"] or component["declared_license"]
        item = {"type": "library", "bom-ref": component["purl"], "name": component["name"], "version": component["version"],
                "purl": component["purl"], "hashes": [{"alg": "SHA-256", "content": component["sha256"]}],
                "properties": [{"name": "mra:wheel-filename", "value": component["filename"]},
                               {"name": "mra:license-status", "value": component["license_status"]},
                               {"name": "mra:license-approval", "value": "not-approved"},
                               {"name": "mra:license-files", "value": json.dumps(component["license_files"], sort_keys=True)}]}
        if license_name and component["license_status"] == "declared_only":
            item["licenses"] = [{"license": {"name": license_name[:8192]}}]
        components.append(item)
    refs = {component["name"]: component["purl"] for component in report["components"]}
    return {"$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json", "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"properties": [{"name": "mra:environment", "value": "public_fixture"},
                {"name": "mra:manifest-sha256", "value": report["manifest_sha256"]},
                {"name": "mra:inventory-sha256", "value": report["inventory_sha256"]},
                {"name": "mra:production-approval", "value": "not-approved"}]}, "components": components,
            "dependencies": [{"ref": refs[name], "dependsOn": [refs[child] for child in children]}
                             for name, children in report["dependency_graph"].items()]}
