"""Offline Windows bootstrap regressions; never invoke the network installer."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import struct
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "Try-Demo.cmd"
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
PAYLOAD_MARKER = "# MRA POWERSHELL PAYLOAD"
RUN_MARKER = "# MRA RUN INSTALLER"


def ps_quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "Windows PowerShell 5.1 bootstrap tests")
class OneClickDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        lines = BOOTSTRAP.read_text(encoding="utf-8").splitlines()
        if lines.count(PAYLOAD_MARKER) != 1 or lines.count(RUN_MARKER) != 1:
            raise AssertionError("bootstrap must have one definition boundary and one invocation boundary")
        start, stop = lines.index(PAYLOAD_MARKER), lines.index(RUN_MARKER)
        if stop <= start:
            raise AssertionError("bootstrap definition boundaries are out of order")
        cls.definitions = "\n".join(lines[start + 1:stop]) + "\n"
        if "try { Start-DemoInstaller; exit" in cls.definitions:
            raise AssertionError("offline function fixture must exclude installer invocation")

    def setUp(self) -> None:
        scratch = ROOT / ".local/verification"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="one-click-tests-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.definitions_file = self.root / "definitions.ps1"
        # PowerShell 5.1 reads UTF-8 with a BOM consistently, including Unicode paths.
        self.definitions_file.write_text(self.definitions, encoding="utf-8-sig", newline="\n")
        self.source = self.root / "source checkout"
        self.receipt = self.root / "ownership.json"
        self.sequence = 0

    def run_functions(self, body: str, *, environment: dict[str, str] | None = None) -> str:
        self.sequence += 1
        script = self.root / f"check-{self.sequence}.ps1"
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)\n"
            f"$definition = [IO.File]::ReadAllText({ps_quote(self.definitions_file)})\n"
            ". ([scriptblock]::Create($definition))\n"
            "try {\n" + body + "\nWrite-Output 'CHECK-PASSED'\n}\n"
            "catch { [Console]::Error.WriteLine($_.Exception.ToString()); exit 1 }\n",
            encoding="utf-8-sig", newline="\n",
        )
        child_environment = dict(os.environ)
        for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial", "MRA_DEMO_HOME"):
            child_environment.pop(name, None)
        child_environment.update(environment or {})
        result = subprocess.run(
            [str(POWERSHELL), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=ROOT, env=child_environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("CHECK-PASSED", result.stdout)
        return result.stdout

    def assert_refused(self, command: str, *, environment: dict[str, str] | None = None) -> str:
        return self.run_functions(
            "$refused = $false\ntry {\n" + command + "\n}\n"
            "catch { $refused = $true; Write-Output ('REFUSED: ' + $_.Exception.Message) }\n"
            "if (-not $refused) { throw 'Unsafe operation was accepted' }",
            environment=environment,
        )

    def make_archive(self, entries: list[tuple[str, bytes]], *, symlink: bool = False) -> Path:
        archive = self.root / f"archive-{self.sequence}-{len(list(self.root.glob('archive-*.zip')))}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            for name, data in entries:
                if symlink:
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    output.writestr(entry, data)
                else:
                    output.writestr(name, data)
        return archive

    def owned_source(self, kind: str = "source") -> dict:
        self.source.mkdir()
        (self.source / "README.md").write_bytes(b"owned source fixture\n")
        package = self.source / "src/package.py"
        package.parent.mkdir()
        package.write_bytes(b"VALUE = 'fixture'\n")
        self.run_functions(f"Save-Inventory {ps_quote(self.source)} {ps_quote(self.receipt)} {ps_quote(kind)} 'fixture-v1'")
        return json.loads(self.receipt.read_text(encoding="utf-8"))

    def assert_inventory(self, kind: str = "source", version: str = "fixture-v1") -> str:
        return f"Assert-Inventory {ps_quote(self.source)} {ps_quote(self.receipt)} {ps_quote(kind)} {ps_quote(version)}"

    def test_sha_and_file_hash_bind_exact_local_bytes(self) -> None:
        file = self.root / "download with spaces.zip"
        content = b"verified bytes\x00\n"
        file.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        self.run_functions(f"if ((Get-Sha256 {ps_quote(file)}) -cne '{digest}') {{ throw 'Wrong digest' }}\n"
                           f"Assert-FileHash {ps_quote(file)} '{digest}'")
        self.assertEqual(file.read_bytes(), content)

    def test_changed_or_missing_download_hash_is_refused_without_replacement(self) -> None:
        file = self.root / "changed.zip"
        file.write_bytes(b"retain changed file")
        self.assert_refused(f"Assert-FileHash {ps_quote(file)} {'0' * 64}")
        self.assert_refused(f"Assert-FileHash {ps_quote(self.root / 'missing.zip')} {'0' * 64}")
        self.assertEqual(file.read_bytes(), b"retain changed file")
        self.assertFalse((self.root / "missing.zip").exists())

    def test_safe_root_is_absolute_and_rejects_relative_network_drive_or_onedrive_paths(self) -> None:
        fresh = self.root / "new installation"
        self.run_functions(f"if ((Assert-SafeRoot {ps_quote(fresh)}) -ine {ps_quote(fresh)}) {{ throw 'Root changed' }}")
        self.assertFalse(fresh.exists())
        for path in ("relative/demo", r"\\invalid.example\share\demo", self.root.anchor,
                     str(self.root / "OneDrive - Example Agency/demo")):
            with self.subTest(path=path):
                self.assert_refused(f"Assert-SafeRoot {ps_quote(path)}")

    def test_configured_onedrive_alias_is_refused_even_without_onedrive_name(self) -> None:
        sync_root = self.root / "synchronized files"
        candidate = sync_root / "demo"
        for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            with self.subTest(variable=name):
                self.assert_refused(f"Assert-SafeRoot {ps_quote(candidate)}", environment={name: str(sync_root)})
        self.assertFalse(sync_root.exists())

    def test_reparse_ancestor_metadata_is_refused_before_new_directory_creation(self) -> None:
        candidate = self.root / "new child"
        # Simulate the OS metadata boundary without requiring symlink privileges.
        self.assert_refused(
            "function Get-Item { param([string]$LiteralPath, [switch]$Force) "
            "return [pscustomobject]@{ Attributes = [IO.FileAttributes]::ReparsePoint } }\n"
            f"Assert-SafeRoot {ps_quote(candidate)}"
        )
        self.assertFalse(candidate.exists())

    def test_valid_archive_strips_only_expected_root_and_retains_exact_bytes(self) -> None:
        archive = self.make_archive([("snapshot/", b""), ("snapshot/README.md", b"readme\n"),
                                     ("snapshot/src/package.py", b"VALUE = 1\n")])
        self.run_functions(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
        self.assertEqual((self.source / "README.md").read_bytes(), b"readme\n")
        self.assertEqual((self.source / "src/package.py").read_bytes(), b"VALUE = 1\n")
        self.assertFalse((self.source / "snapshot").exists())

    def test_archive_traversal_windows_paths_absolute_paths_and_wrong_prefix_are_refused(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_bytes(b"preserve outside target\n")
        for name in ("snapshot/../outside.txt", r"snapshot\..\outside.txt", "/absolute.txt",
                     "snapshot/C:outside.txt", "unrelated/file.txt"):
            with self.subTest(entry=name):
                archive = self.make_archive([(name, b"must not be written")])
                self.assert_refused(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
                self.assertFalse(self.source.exists())
                self.assertEqual(outside.read_bytes(), b"preserve outside target\n")

    def test_archive_case_insensitive_duplicate_paths_are_refused_before_extraction(self) -> None:
        archive = self.make_archive([("snapshot/Model.py", b"first"), ("snapshot/model.py", b"second")])
        self.assert_refused(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
        self.assertFalse(self.source.exists())

    def test_archive_unix_symlink_entries_are_refused_before_extraction(self) -> None:
        archive = self.make_archive([("snapshot/linked.py", b"../outside.txt")], symlink=True)
        self.assert_refused(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
        self.assertFalse(self.source.exists())

    def test_declared_oversized_archive_member_is_refused_without_allocating_large_fixture(self) -> None:
        archive = self.make_archive([("snapshot/large.bin", b"tiny")])
        raw = bytearray(archive.read_bytes())
        central = raw.index(b"PK\x01\x02")
        local = raw.index(b"PK\x03\x04")
        struct.pack_into("<I", raw, central + 24, 128 * 1024 * 1024)
        struct.pack_into("<I", raw, local + 22, 128 * 1024 * 1024)
        archive.write_bytes(raw)
        diagnostic = self.assert_refused(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
        self.assertIn("extraction limits", diagnostic)
        self.assertFalse(self.source.exists())

    def test_existing_archive_target_is_preserved_and_never_repaired(self) -> None:
        self.source.mkdir()
        sentinel = self.source / "existing.txt"
        sentinel.write_bytes(b"existing or partial installation\n")
        archive = self.make_archive([("snapshot/new.txt", b"new file")])
        self.assert_refused(f"Expand-VerifiedArchive {ps_quote(archive)} {ps_quote(self.source)} 'snapshot/'")
        self.assertEqual(list(self.source.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"existing or partial installation\n")

    def test_complete_owned_inventory_reuses_without_rewriting_receipt_or_files(self) -> None:
        record = self.owned_source()
        before = self.receipt.read_bytes()
        files = {path.relative_to(self.source).as_posix(): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        self.run_functions(self.assert_inventory())
        self.assertEqual(record["schema"], "mra-demo-archive/v1")
        self.assertEqual(self.receipt.read_bytes(), before)
        self.assertEqual({path.relative_to(self.source).as_posix(): path.read_bytes() for path in self.source.rglob("*") if path.is_file()}, files)

    def test_changed_or_missing_owned_source_files_are_refused_without_repair(self) -> None:
        self.owned_source()
        before = self.receipt.read_bytes()
        readme = self.source / "README.md"
        readme.write_bytes(b"changed source retained")
        self.assert_refused(self.assert_inventory())
        self.assertEqual(readme.read_bytes(), b"changed source retained")
        readme.unlink()
        self.assert_refused(self.assert_inventory())
        self.assertFalse(readme.exists())
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_unowned_partial_source_or_runtime_is_refused_without_receipt_creation(self) -> None:
        self.source.mkdir()
        file = self.source / "partial.bin"
        file.write_bytes(b"diagnostic fragment")
        for kind in ("source", "python"):
            with self.subTest(kind=kind):
                self.assert_refused(self.assert_inventory(kind))
        self.assertEqual(file.read_bytes(), b"diagnostic fragment")
        self.assertFalse(self.receipt.exists())

    def test_inventory_kind_version_and_directory_are_exact_boundaries(self) -> None:
        record = self.owned_source()
        self.assert_refused(self.assert_inventory("python"))
        self.assert_refused(self.assert_inventory(version="another-version"))
        record["directory"] = str(self.root / "another checkout")
        self.receipt.write_text(json.dumps(record), encoding="utf-8")
        before = self.receipt.read_bytes()
        self.assert_refused(self.assert_inventory())
        self.assertEqual(self.receipt.read_bytes(), before)

    def test_unsafe_or_case_duplicate_inventory_entries_are_refused(self) -> None:
        record = self.owned_source()
        for path in ("../outside.txt", r"src\package.py", "/absolute.txt", "C:outside.txt", "readme.md"):
            with self.subTest(path=path):
                value = {**record, "files": [*record["files"], {"path": path, "sha256": "0" * 64}]}
                self.receipt.write_text(json.dumps(value), encoding="utf-8")
                self.assert_refused(self.assert_inventory())
                self.assertEqual(json.loads(self.receipt.read_text(encoding="utf-8")), value)

    def test_source_allows_only_generated_local_and_editable_metadata_extras(self) -> None:
        self.owned_source()
        for relative in (".local/temp/diagnostic.txt", "src/model_release_assurance.egg-info/PKG-INFO"):
            file = self.source / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"generated fixture")
        self.run_functions(self.assert_inventory())
        unexpected = self.source / "untracked-package.py"
        unexpected.write_bytes(b"unexpected source fixture")
        self.assert_refused(self.assert_inventory())
        self.assertEqual(unexpected.read_bytes(), b"unexpected source fixture")

    def test_runtime_inventory_rejects_generated_extra_files_too(self) -> None:
        self.owned_source("python")
        extra = self.source / ".local/generated.txt"
        extra.parent.mkdir()
        extra.write_bytes(b"not part of verified runtime")
        self.assert_refused(self.assert_inventory("python"))
        self.assertEqual(extra.read_bytes(), b"not part of verified runtime")

    def test_new_text_writer_never_overwrites_existing_ownership_file(self) -> None:
        file = self.root / "ownership-marker.json"
        file.write_bytes(b"retain existing ownership")
        self.assert_refused(f"Write-NewText {ps_quote(file)} 'replacement'")
        self.assertEqual(file.read_bytes(), b"retain existing ownership")

    def test_corrupt_cached_download_is_refused_before_any_network_attempt(self) -> None:
        file = self.root / "cached.zip"
        file.write_bytes(b"retain corrupt cached download")
        self.assert_refused(f"Get-Download 'https://must-not-contact.invalid/fixture.zip' {ps_quote(file)} {'0' * 64}")
        self.assertEqual(file.read_bytes(), b"retain corrupt cached download")
        self.assertFalse(Path(str(file) + ".partial").exists())

    def test_interrupted_download_is_retained_and_refused_without_network_retry(self) -> None:
        file = self.root / "interrupted.zip"
        partial = Path(str(file) + ".partial")
        partial.write_bytes(b"retain interrupted diagnostic")
        self.assert_refused(f"Get-Download 'https://must-not-contact.invalid/fixture.zip' {ps_quote(file)} {'0' * 64}")
        self.assertEqual(partial.read_bytes(), b"retain interrupted diagnostic")
        self.assertFalse(file.exists())


    def test_complete_verified_partial_download_is_recovered_without_network(self) -> None:
        file = self.root / "completed-download.zip"
        partial = Path(str(file) + ".partial")
        content = b"complete verified download retained after interruption\n"
        partial.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        self.run_functions(
            "$script:networkRequests = 0\n"
            "function New-Object { param([Parameter(Position=0)][string]$TypeName, "
            "[Parameter(Position=1)][object[]]$ArgumentList) "
            "if ($TypeName -in @('Net.WebClient','System.Net.WebClient')) { $script:networkRequests++; "
            "throw 'Network object creation must not be reached' }; "
            "if ($ArgumentList.Count -gt 0) { Microsoft.PowerShell.Utility\\New-Object -TypeName $TypeName -ArgumentList $ArgumentList } "
            "else { Microsoft.PowerShell.Utility\\New-Object -TypeName $TypeName } }\n"
            f"Get-Download 'https://must-not-contact.invalid/fixture.zip' {ps_quote(file)} '{digest}'\n"
            "if ($script:networkRequests -ne 0) { throw 'Network was attempted during recovery' }"
        )
        self.assertEqual(file.read_bytes(), content)
        self.assertFalse(partial.exists())

    def test_embedded_dataset_helper_matches_repository_bytes_and_checksum(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        payloads = re.findall(r"^\$DataProbeBase64 = '([A-Za-z0-9+/=]+)'$", text, re.MULTILINE)
        digests = re.findall(r"^\$DataProbeHash = '([0-9a-f]{64})'$", text, re.MULTILINE)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(len(digests), 1)
        decoded = base64.b64decode(payloads[0], validate=True)
        self.assertEqual(decoded, (ROOT / "scripts/prepare_demo_data.py").read_bytes())
        self.assertEqual(hashlib.sha256(decoded).hexdigest(), digests[0])

    def test_inventory_roundtrip_supports_unicode_custom_install_directory(self) -> None:
        self.source = self.root / "demo café 数据"
        self.owned_source()
        before = self.receipt.read_bytes()
        self.run_functions(self.assert_inventory())
        self.assertEqual(self.receipt.read_bytes(), before)
        self.assertTrue((self.source / "README.md").is_file())

if __name__ == "__main__":
    unittest.main()
