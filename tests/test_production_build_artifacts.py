"""Small inert wheel fixtures exercise explicit-target locks without installing code."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings
import zipfile

from packaging.tags import parse_tag

from model_release_assurance.production_build import artifacts as build


class ProductionBuildArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-wheel-lock-")
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.house = self.parent / "wheels"
        self.house.mkdir()

    def wheel(self, name="demo", version="1.0", *, requires=(), extras=(), tag="py3-none-any", wheel_tags=None,
              metadata_name=None, metadata_version=None, metadata_format="2.4", license_value="MIT", python_spec=None, members=(), house=None):
        house = house or self.house
        escaped = name.replace("-", "_")
        filename = f"{escaped}-{version}-{tag}.whl"
        dist = f"{escaped}-{version}.dist-info"
        headers = ["Metadata-Version: " + metadata_format, "Name: " + (metadata_name or name), "Version: " + (metadata_version or version)]
        headers += ["Requires-Dist: " + value for value in requires]
        headers += ["Provides-Extra: " + value for value in extras]
        if license_value is not None:
            headers += ["License: " + license_value]
        if python_spec:
            headers += ["Requires-Python: " + python_spec]
        headers += ["License-File: LICENSE.txt"]
        wheel_tags = wheel_tags or sorted(str(value) for value in parse_tag(tag))
        wheel_headers = ["Wheel-Version: 1.0", "Root-Is-Purelib: true"] + ["Tag: " + value for value in wheel_tags]
        contents = [(escaped + "/__init__.py", b"raise AssertionError('Fixture code must never execute')\n"),
                    (dist + "/METADATA", ("\n".join(headers) + "\n\n").encode()),
                    (dist + "/WHEEL", ("\n".join(wheel_headers) + "\n\n").encode()),
                    (dist + "/licenses/LICENSE.txt", b"Fixture declared license evidence; no legal approval.\n")]
        contents.extend(members)
        path = house / filename
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for member, content in contents:
                    archive.writestr(member, content)
        return {"name": name, "version": version, "filename": filename,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}

    def manifest(self, artifacts, *, roots=None, platform="win_amd64"):
        return {"schema": "mra-wheel-lock/v1", "environment": "public_fixture",
                "target": {"python_version": "3.12", "python_full_version": "3.12.14", "implementation": "cpython", "platform": platform},
                "roots": roots or [artifact["name"] + "==" + artifact["version"] for artifact in artifacts], "artifacts": artifacts}

    def verify(self, manifest, house=None):
        return build.verify_wheel_bundle(manifest, house or self.house)

    def test_pinned_wheel_report_and_cyclonedx_bind_hashes_and_declared_license_files(self):
        artifact = self.wheel()
        manifest = self.manifest([artifact])
        before = (self.house / artifact["filename"]).read_bytes()
        report = self.verify(manifest)
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["manifest_sha256"], build.canonical_sha256(manifest))
        self.assertEqual(report["inventory_sha256"], build.canonical_sha256([artifact]))
        self.assertEqual(report["dependency_graph"], {"demo": []})
        self.assertFalse(report["production_approved"])
        self.assertFalse(report["license_approved"])
        component = report["components"][0]
        self.assertEqual(component["purl"], "pkg:pypi/demo@1.0")
        self.assertEqual(component["license_status"], "declared_only")
        self.assertEqual(len(component["license_files"]), 1)
        sbom = build.build_cyclonedx_sbom(report)
        self.assertEqual(sbom["specVersion"], "1.6")
        self.assertEqual(sbom["components"][0]["hashes"], [{"alg": "SHA-256", "content": artifact["sha256"]}])
        self.assertEqual(sbom["components"][0]["licenses"], [{"license": {"name": "MIT"}}])
        self.assertEqual(before, (self.house / artifact["filename"]).read_bytes())
        self.assertEqual(len(list(self.house.iterdir())), 1)

    def test_complete_dependency_closure_propagates_requested_extras_transitively(self):
        root = self.wheel("root", requires=['middle[crypto]>=2; python_version >= "3.12"'], extras=["full"])
        middle = self.wheel("middle", "2.0", requires=['crypto>=3; extra == "crypto"'], extras=["crypto"])
        crypto = self.wheel("crypto", "3.0")
        report = self.verify(self.manifest([root, middle, crypto], roots=["root[full]==1.0"]))
        self.assertEqual(report["dependency_graph"], {"crypto": [], "middle": ["crypto"], "root": ["middle"]})
        sbom = build.build_cyclonedx_sbom(report)
        self.assertIn({"ref": "pkg:pypi/middle@2.0", "dependsOn": ["pkg:pypi/crypto@3.0"]}, sbom["dependencies"])

    def test_cross_platform_markers_use_complete_target_environment_not_host(self):
        for platform, expected in (("win_amd64", "windows-leaf"), ("manylinux_2_28_x86_64", "linux-leaf")):
            house = self.parent / platform
            house.mkdir()
            root = self.wheel("root", requires=['windows-leaf; sys_platform == "win32"', 'linux-leaf; sys_platform == "linux"'], house=house)
            leaf = self.wheel(expected, house=house)
            manifest = self.manifest([root, leaf], roots=["root==1.0"], platform=platform)
            with mock.patch("packaging.markers.default_environment", return_value={"sys_platform": "wrong-host"}):
                report = self.verify(manifest, house)
            self.assertEqual(report["dependency_graph"]["root"], [expected])
            self.assertEqual(report["marker_environment"]["sys_platform"], "win32" if platform == "win_amd64" else "linux")
            self.assertEqual(report["marker_environment"]["python_full_version"], "3.12.14")

    def test_missing_incompatible_undeclared_extra_and_unreachable_dependencies_fail(self):
        root = self.wheel("root", requires=["dependency>=2"])
        with self.assertRaisesRegex(build.ArtifactError, "Missing or incompatible"):
            self.verify(self.manifest([root], roots=["root==1.0"]))
        dependency = self.wheel("dependency", "1.0")
        with self.assertRaisesRegex(build.ArtifactError, "Missing or incompatible"):
            self.verify(self.manifest([root, dependency], roots=["root==1.0"]))
        with self.assertRaisesRegex(build.ArtifactError, "extra is not declared"):
            self.verify(self.manifest([root, dependency], roots=["root[unavailable]==1.0"]))
        root = self.wheel("root")
        with self.assertRaisesRegex(build.ArtifactError, "outside.*closure"):
            self.verify(self.manifest([root, dependency], roots=["root==1.0"]))

    def test_inactive_extra_does_not_require_or_admit_unrequested_dependency(self):
        root = self.wheel("root", requires=['extra-leaf; extra == "extended"'], extras=["extended"])
        report = self.verify(self.manifest([root], roots=["root==1.0"]))
        self.assertEqual(report["dependency_graph"], {"root": []})
        with self.assertRaisesRegex(build.ArtifactError, "Missing or incompatible"):
            self.verify(self.manifest([root], roots=["root[extended]==1.0"]))

    def test_direct_urls_and_unspecified_platform_markers_are_never_accepted(self):
        for requirement in ('leaf @ https://example.invalid/leaf.whl', 'leaf; platform_release == "unknown"',
                            'leaf; platform_version != ""'):
            artifact = self.wheel(requires=[requirement])
            with self.subTest(requirement=requirement), self.assertRaises(build.ArtifactError):
                self.verify(self.manifest([artifact]))
        artifact = self.wheel()
        for requirement in ("demo>=1", "demo==1.*", "demo @ https://example.invalid/demo.whl"):
            with self.subTest(root=requirement), self.assertRaises(build.ArtifactError):
                build.validate_manifest(self.manifest([artifact], roots=[requirement]))

    def test_hash_size_extra_files_and_missing_files_are_checked_before_metadata(self):
        artifact = self.wheel()
        manifest = self.manifest([artifact])
        wrong_hash = deepcopy(manifest)
        wrong_hash["artifacts"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(build.ArtifactError, "hash differs"):
            self.verify(wrong_hash)
        wrong_size = deepcopy(manifest)
        wrong_size["artifacts"][0]["size_bytes"] += 1
        with self.assertRaises(build.ArtifactError):
            self.verify(wrong_size)
        extra = self.house / "notes.txt"
        extra.write_text("not permitted", encoding="utf-8")
        with self.assertRaisesRegex(build.ArtifactError, "no extras"):
            self.verify(manifest)
        extra.unlink()
        (self.house / artifact["filename"]).unlink()
        with self.assertRaisesRegex(build.ArtifactError, "no extras"):
            self.verify(manifest)

    def test_metadata_identity_requires_python_and_wheel_tag_mismatches_fail(self):
        for changes in ({"metadata_name": "another"}, {"metadata_version": "9.0"}, {"python_spec": ">=3.13"},
                        {"wheel_tags": ["cp312-cp312-win_amd64"]}):
            artifact = self.wheel(**changes)
            with self.subTest(changes=changes), self.assertRaises(build.ArtifactError):
                self.verify(self.manifest([artifact]))

    def test_manylinux_older_baselines_abi3_and_platform_independence_are_explicit(self):
        good = self.wheel(tag="cp38-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64")
        report = self.verify(self.manifest([good], platform="manylinux_2_28_x86_64"))
        self.assertEqual(report["status"], "verified")
        with self.assertRaisesRegex(build.ArtifactError, "explicit target"):
            self.verify(self.manifest([good], platform="win_amd64"))
        (self.house / good["filename"]).unlink()
        for tag in ("cp312-cp312-manylinux_2_34_x86_64", "cp313-cp313-manylinux_2_28_x86_64", "cp312-cp312-linux_x86_64"):
            artifact = self.wheel(tag=tag)
            with self.subTest(tag=tag), self.assertRaisesRegex(build.ArtifactError, "explicit target"):
                self.verify(self.manifest([artifact], platform="manylinux_2_28_x86_64"))
            (self.house / artifact["filename"]).unlink()

    def test_zip_traversal_duplicate_link_and_encryption_are_rejected(self):
        linked = zipfile.ZipInfo("demo/linked")
        linked.create_system = 3
        linked.external_attr = (stat.S_IFLNK | 0o777) << 16
        for members in ((('../escape.py', b"bad"),), (("demo/__init__.py", b"duplicate"),), ((linked, b"target"),),
                        (("C:/absolute.py", b"bad"),), (("demo\\outside.py", b"bad"),)):
            artifact = self.wheel(members=members)
            if isinstance(members[0][0], str) and "\\" in members[0][0]:
                # Windows ZipInfo normalizes separators when writing; patch both
                # stored header names to exercise a genuinely hostile ZIP path.
                path = self.house / artifact["filename"]
                content = path.read_bytes().replace(b"demo/outside.py", b"demo\\outside.py")
                path.write_bytes(content)
                artifact.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
            with self.subTest(members=members), self.assertRaises(build.ArtifactError):
                self.verify(self.manifest([artifact]))
        artifact = self.wheel()
        path = self.house / artifact["filename"]
        content = bytearray(path.read_bytes())
        central = content.index(b"PK\x01\x02")
        flags = struct.unpack_from("<H", content, central + 8)[0]
        struct.pack_into("<H", content, central + 8, flags | 1)
        path.write_bytes(content)
        artifact.update(sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
        with self.assertRaisesRegex(build.ArtifactError, "encrypted"):
            self.verify(self.manifest([artifact]))

    def test_unknown_metadata_and_windows_filename_aliases_are_rejected(self):
        for metadata_format in ("garbage", "99.0", "2.0"):
            artifact = self.wheel(metadata_format=metadata_format)
            with self.subTest(metadata_format=metadata_format), self.assertRaisesRegex(build.ArtifactError, "metadata version"):
                self.verify(self.manifest([artifact]))
        for name in ("demo/mod.py.", "demo/mod.py ", "demo/CON.txt", "demo/LPT1", "demo/COM¹.txt", "demo/bad?.txt"):
            artifact = self.wheel(members=[(name, b"unsafe")])
            with self.subTest(name=name), self.assertRaisesRegex(build.ArtifactError, "Win32-ambiguous"):
                self.verify(self.manifest([artifact]))
        artifact = self.wheel(members=[("demo", b"collides with package directory")])
        with self.assertRaisesRegex(build.ArtifactError, "prefix collision"):
            self.verify(self.manifest([artifact]))

    def test_zip_expansion_is_rejected_before_any_metadata_member_is_opened(self):
        artifact = self.wheel(members=[("demo/bomb.bin", b"0" * (2 * 1024 * 1024))])
        with mock.patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("Must not expand unsafe ZIP")), self.assertRaisesRegex(build.ArtifactError, "expansion"):
            self.verify(self.manifest([artifact]))

    def test_filesystem_hardlink_and_reparse_substitution_fail_closed(self):
        artifact = self.wheel()
        manifest = self.manifest([artifact])
        path = self.house / artifact["filename"]
        alias = self.parent / "alias.whl"
        os.link(path, alias)
        with self.assertRaises(build.ArtifactError):
            self.verify(manifest)
        alias.unlink()
        original_lstat = Path.lstat
        def reparse(candidate, *args, **kwargs):
            if candidate == path:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0x400)
            return original_lstat(candidate, *args, **kwargs)
        with mock.patch.object(Path, "lstat", reparse), self.assertRaises(build.ArtifactError):
            self.verify(manifest)
        self.assertEqual(self.verify(manifest)["status"], "verified")

    def test_exact_manifest_fields_and_strict_json_reject_ambiguity(self):
        artifact = self.wheel()
        manifest = self.manifest([artifact])
        parsed = build.validate_manifest(manifest)
        parsed["artifacts"][0]["name"] = "changed"
        self.assertEqual(manifest["artifacts"][0]["name"], "demo")
        for location in ((), ("target",), ("artifacts", 0)):
            value = deepcopy(manifest)
            node = value
            for part in location:
                node = node[part]
            node["unknown"] = True
            with self.assertRaises(build.ArtifactError):
                build.validate_manifest(value)
        for field, value in (("name", "Demo"), ("filename", "../demo.whl"), ("size_bytes", True), ("sha256", "G" * 64)):
            invalid = deepcopy(manifest)
            invalid["artifacts"][0][field] = value
            with self.subTest(field=field), self.assertRaises(build.ArtifactError):
                build.validate_manifest(invalid)
        content = json.dumps(manifest)
        for invalid in (content.replace('"schema":', '"schema":"duplicate","schema":', 1),
                        content.replace(str(artifact["size_bytes"]), "NaN", 1),
                        content.replace(str(artifact["size_bytes"]), "9" * 5000, 1)):
            with self.assertRaises(build.ArtifactError):
                build.parse_manifest_json(invalid)

    def test_unknown_license_is_retained_as_unknown_without_invented_spdx_or_approval(self):
        for declaration in (None, "UNKNOWN"):
            artifact = self.wheel(license_value=declaration)
            report = self.verify(self.manifest([artifact]))
            self.assertEqual(report["components"][0]["license_status"], "unknown")
            self.assertFalse(report["license_approved"])
            component = build.build_cyclonedx_sbom(report)["components"][0]
            self.assertNotIn("licenses", component)
            self.assertIn({"name": "mra:license-status", "value": "unknown"}, component["properties"])


if __name__ == "__main__":
    unittest.main()
