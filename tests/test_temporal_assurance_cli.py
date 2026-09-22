import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model_release_assurance.temporal_assurance import AssuranceStore
from model_release_assurance.temporal_assurance.__main__ import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "state.sqlite3"
        store = AssuranceStore(self.path, budget_micros=1_000_000, scope_digest="a"*64)
        until = int(time.time()) + 3600
        evidence = store.register_evidence(b"trusted toy provenance", expires_at=until)
        store.register_dataset("b"*64, record_ids=["record"], evidence_digest=evidence, expires_at=until)
        store.register_cache("cache", cache_digest="c"*64, epsilon_micros=1_000_000, record_ids=["record"], evidence_digest=evidence, expires_at=until)
        store.register_model("model", cache_id="cache", dataset_digest="b"*64, record_ids=["record"], artifact_bytes=b"allowed artifact", evidence_digest=evidence, expires_at=until)
        store.register_authority("operator", expires_at=until)

    def command(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["--db", str(self.path), *args])
        return code, json.loads(stream.getvalue())

    def test_prepare_commit_download_and_revocation(self):
        self.assertEqual(self.command("prepare", "--request", "r1", "--model", "model", "--authority", "operator", "--expected-revision", "0")[0], 0)
        out = self.root / "download.zip"
        self.assertEqual(self.command("download", "--request", "r1", "--authority", "operator", "--output", str(out))[0], 2)
        self.assertFalse(out.exists())
        self.assertEqual(self.command("commit", "--request", "r1")[0], 0)
        self.assertEqual(self.command("download", "--request", "r1", "--authority", "operator", "--output", str(out))[0], 0)
        self.assertEqual(out.read_bytes(), b"allowed artifact")
        self.assertEqual(self.command("download", "--request", "r1", "--authority", "operator", "--output", str(out))[0], 2)
        self.assertEqual(self.command("revoke", "--request", "r1")[0], 0)
        self.assertEqual(self.command("download", "--request", "r1", "--authority", "operator", "--output", str(self.root / "new.zip"))[0], 2)
        code, result = self.command("status")
        self.assertEqual(code, 0)
        self.assertEqual(result["maximum_spent_epsilon"], 1)
        self.assertNotIn("charges", result)

    def test_missing_ledger_is_not_silently_created(self):
        path = self.root / "missing.sqlite3"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db", str(path), "status"]), 2)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
