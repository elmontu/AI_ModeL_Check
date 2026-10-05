"""Public-fixture supply-chain CLI uses inert wheels and mocked network only."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from urllib.request import Request
import zipfile

SPEC = importlib.util.spec_from_file_location("mra_supply_chain_cli", Path(__file__).resolve().parents[1] / "scripts/verify_build_supply_chain.py")
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
NOW = 1800000000
REPORTS = {"inventory.json", "sbom.cdx.json", "observations.json", "advisories.json", "license-review.json", "result.json"}


def fixture_wheel(path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        wheel.writestr("demo/__init__.py", "raise AssertionError('Never execute fixture wheels')\n")
        wheel.writestr("demo-1.0.dist-info/METADATA", "Metadata-Version: 2.4\nName: demo\nVersion: 1.0\nLicense: UNKNOWN\n\n")
        wheel.writestr("demo-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n")
    content = path.read_bytes()
    return {"name": "demo", "version": "1.0", "filename": path.name,
            "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)}


@unittest.skipUnless(shutil.which("git"), "Git is required for ignored output validation")
class ProductionBuildCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mra-supply-chain-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True)
        (self.root / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.house = self.root / "wheels"
        self.house.mkdir()
        self.item = fixture_wheel(self.house / "demo-1.0-py3-none-any.whl")
        self.manifest = {"schema": "mra-wheel-lock/v1", "environment": "public_fixture",
                         "target": {"python_version": "3.12", "python_full_version": "3.12.14",
                                    "implementation": "cpython", "platform": "win_amd64"},
                         "roots": ["demo==1.0"], "artifacts": [self.item]}
        self.manifest_path = self.root / "demo.json"
        self.requirements_path = self.root / "demo.requirements.txt"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.requirements = f"demo==1.0 --hash=sha256:{self.item['sha256']}\n"
        self.requirements_path.write_text("# Exact inert fixture\n" + self.requirements, encoding="utf-8")
        self.metadata = {"info": {"name": "demo", "version": "1.0"}, "vulnerabilities": [],
                         "urls": [{"filename": self.item["filename"], "packagetype": "bdist_wheel", "yanked": False,
                                   "size": self.item["size_bytes"], "digests": {"sha256": self.item["sha256"]},
                                   "url": "https://files.pythonhosted.org/packages/demo-1.0-py3-none-any.whl"}]}
        self.calls = []

    def fetch(self, url, *, maximum, host):
        self.calls.append((url, maximum, host))
        if host == "pypi.org":
            self.assertEqual(url, "https://pypi.org/pypi/demo/1.0/json")
            return json.dumps(self.metadata).encode()
        self.assertEqual(host, "files.pythonhosted.org")
        return (self.house / self.item["filename"]).read_bytes()

    def run_cli(self, **changes):
        options = dict(root=self.root, manifest_path=self.manifest_path, output=".local/run",
                       wheelhouse=self.house, scan_pypi=True, fetcher=self.fetch, now=NOW)
        options.update(changes)
        result = CLI.run_supply_chain(**options)
        self.assertFalse(result["source_verified"])
        self.assertFalse(result["deployable"])
        self.assertFalse(result["production_authorized"])
        self.assertFalse(result["license_approved"])
        return result

    def document(self, name, output="run"):
        return json.loads((self.root / ".local" / output / name).read_text(encoding="utf-8"))

    def test_existing_bundle_scan_retains_exact_reports_and_pending_license(self):
        result = self.run_cli()
        self.assertEqual(result["status"], "passed")
        self.assertEqual({path.name for path in (self.root / ".local/run").iterdir()}, REPORTS)
        inventory = self.document("inventory.json")
        self.assertEqual(inventory["status"], "verified")
        self.assertEqual(self.document("sbom.cdx.json")["specVersion"], "1.6")
        observations = self.document("observations.json")
        self.assertIsInstance(observations, list)
        self.assertEqual(len(observations), 1)
        self.assertEqual(self.document("advisories.json")["inventory_sha256"], inventory["inventory_sha256"])
        self.assertTrue(self.document("advisories.json")["coverage_complete"])
        self.assertEqual(self.document("license-review.json")["status"], "pending_agency_review")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result, self.document("result.json"))

    def test_download_reuses_exact_version_body_and_exclusive_verified_wheel(self):
        result = self.run_cli(download=True, wheelhouse=None)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual((self.root / ".local/run/wheelhouse" / self.item["filename"]).read_bytes(),
                         (self.house / self.item["filename"]).read_bytes())
        self.assertEqual(self.document("observations.json")[0]["response_sha256"],
                         hashlib.sha256(json.dumps(self.metadata).encode()).hexdigest())

    def test_omitted_scan_is_incomplete_and_performs_no_metadata_fetch(self):
        result = self.run_cli(scan_pypi=False)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["wheel_bundle_verified"])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.document("observations.json"), [])
        self.assertFalse(self.document("advisories.json")["coverage_complete"])

    def test_download_without_scan_does_not_claim_observed_advisory_coverage(self):
        result = self.run_cli(download=True, wheelhouse=None, scan_pypi=False)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["wheel_bundle_verified"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.document("observations.json"), [])

    def test_failed_scan_is_a_persisted_error_observation(self):
        result = self.run_cli(fetcher=mock.Mock(side_effect=OSError("private proxy detail must not appear")))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.document("observations.json")[0]["status"], "error")
        self.assertIn("observation_error", self.document("advisories.json")["reasons"])
        self.assertNotIn("private proxy", json.dumps(result))

    def test_vulnerability_or_wrong_version_cannot_pass(self):
        self.metadata["vulnerabilities"] = [{"id": "PYSEC-FIXTURE-1"}]
        result = self.run_cli()
        self.assertEqual(result["status"], "failed")
        self.assertTrue(self.document("advisories.json")["coverage_complete"])
        self.assertEqual(len(self.document("advisories.json")["findings"]), 1)
        self.metadata["info"]["version"] = "2.0"
        result = self.run_cli(output=".local/wrong-version")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.document("observations.json", "wrong-version")[0]["status"], "error")

    def test_requirements_drift_fails_before_network_and_retains_all_receipts(self):
        self.requirements_path.write_text(self.requirements.replace("demo==1.0", "demo==2.0"), encoding="utf-8")
        result = self.run_cli()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.calls, [])
        self.assertEqual({p.name for p in (self.root / ".local/run").iterdir()}, REPORTS)
        self.assertEqual(self.document("inventory.json")["status"], "unavailable")
        self.assertIn("Requirements differ", result["errors"][0])

    def test_requirements_reject_duplicate_extra_or_option_and_accept_explicit_path(self):
        for content in (self.requirements * 2, self.requirements + "other==1.0\n", "--index-url https://elsewhere.invalid\n" + self.requirements):
            with self.subTest(content=content), self.assertRaises(CLI.SupplyChainError):
                CLI.validate_requirements(content.encode(), self.manifest)
        explicit = self.root / "explicit.txt"
        self.requirements_path.unlink()
        explicit.write_text(self.requirements, encoding="utf-8")
        self.assertEqual(self.run_cli(requirements_path=explicit)["status"], "passed")

    def test_changed_local_wheel_and_downloaded_wrong_hash_fail(self):
        wheel = self.house / self.item["filename"]
        content = wheel.read_bytes()
        wheel.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
        self.assertEqual(self.run_cli()["status"], "failed")
        self.assertFalse(self.document("result.json")["wheel_bundle_verified"])
        result = self.run_cli(output=".local/download-bad", download=True, wheelhouse=None)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(list((self.root / ".local/download-bad/wheelhouse").iterdir()), [])

    def test_untrusted_url_or_yanked_wrong_identity_is_rejected_before_wheel_fetch(self):
        original = deepcopy(self.metadata)
        cases = [("url", "https://evil.example/wheel"), ("url", "http://files.pythonhosted.org/wheel"),
                 ("url", "https://user:secret@files.pythonhosted.org/wheel"), ("yanked", True),
                 ("size", self.item["size_bytes"] + 1), ("digests", {"sha256": "0" * 64})]
        for index, (field, value) in enumerate(cases):
            self.metadata = deepcopy(original)
            self.metadata["urls"][0][field] = value
            self.calls.clear()
            result = self.run_cli(output=f".local/bad-{index}", download=True, wheelhouse=None)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(self.calls), 1)

    def test_duplicate_json_manifest_and_input_drift_fail_with_evidence(self):
        original = self.manifest_path.read_bytes()
        self.manifest_path.write_bytes(original.replace(b'"schema":', b'"schema":"duplicate","schema":', 1))
        self.assertEqual(self.run_cli()["status"], "failed")
        self.assertEqual(self.calls, [])
        self.manifest_path.write_bytes(original)
        def changing_fetch(*args, **kwargs):
            self.requirements_path.write_text(self.requirements + "# changed during verification\n", encoding="utf-8")
            return self.fetch(*args, **kwargs)
        result = self.run_cli(output=".local/drift", fetcher=changing_fetch)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Input changed", result["errors"][0])

    def test_existing_or_traversing_output_is_refused_without_changes(self):
        self.run_cli()
        before = {p.name: p.read_bytes() for p in (self.root / ".local/run").iterdir()}
        with self.assertRaises(CLI._BASELINE.BaselineError):
            self.run_cli()
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / ".local/run").iterdir()})
        for path in (".local/../outside", "reports/new"):
            with self.subTest(path=path), self.assertRaises(CLI._BASELINE.BaselineError):
                self.run_cli(output=path)
        self.assertFalse((self.root / "outside").exists())
        self.assertFalse((self.root / "reports").exists())

    def test_cli_exit_status_is_zero_only_with_verified_clean_advisories(self):
        with mock.patch.object(CLI, "ROOT", self.root), mock.patch.object(CLI, "fetch_public", self.fetch), mock.patch("sys.stdout", new_callable=io.StringIO):
            flags = ["--manifest", str(self.manifest_path), "--wheelhouse", str(self.house)]
            self.assertEqual(CLI.main(flags + ["--scan-pypi", "--output", ".local/clean"]), 0)
            self.assertEqual(CLI.main(flags + ["--output", ".local/no-scan"]), 1)
            self.assertEqual(CLI.main(flags + ["--scan-pypi", "--output", ".local/clean"]), 2)


class PublicFetchPolicyTests(unittest.TestCase):
    def response(self, *, url="https://pypi.org/pypi/demo/1.0/json", body=b"{}", headers=None):
        result = mock.MagicMock()
        result.__enter__.return_value = result
        result.status = 200
        result.geturl.return_value = url
        result.headers = headers or {}
        result.read.return_value = body
        return result

    def test_redirects_cannot_cross_host_protocol_or_credential_boundary(self):
        handler = CLI._SameHostRedirect("pypi.org")
        request = Request("https://pypi.org/pypi/demo/1.0/json")
        for target in ("https://files.pythonhosted.org/file", "http://pypi.org/file", "https://pypi.org:443/file", "https://name@pypi.org/file"):
            with self.subTest(target=target), self.assertRaises(CLI.SupplyChainError):
                handler.redirect_request(request, None, 302, "redirect", {}, target)
        redirected = handler.redirect_request(request, None, 302, "redirect", {}, "https://pypi.org/other")
        self.assertEqual(redirected.full_url, "https://pypi.org/other")

    def test_fetch_checks_final_host_size_encoding_and_bounded_read(self):
        response = self.response()
        with mock.patch.object(CLI, "build_opener") as opener:
            opener.return_value.open.return_value = response
            self.assertEqual(CLI.fetch_public("https://pypi.org/pypi/demo/1.0/json", maximum=10, host="pypi.org"), b"{}")
            response.read.assert_called_once_with(11)
        for changed in (dict(url="https://evil.example/file"), dict(body=b"x" * 11),
                        dict(headers={"Content-Length": "11"}), dict(headers={"Content-Length": "3"}),
                        dict(headers={"Content-Encoding": "gzip"})):
            with self.subTest(changed=changed), mock.patch.object(CLI, "build_opener") as opener:
                opener.return_value.open.return_value = self.response(**changed)
                with self.assertRaises(CLI.SupplyChainError):
                    CLI.fetch_public("https://pypi.org/pypi/demo/1.0/json", maximum=10, host="pypi.org")


if __name__ == "__main__":
    unittest.main()
