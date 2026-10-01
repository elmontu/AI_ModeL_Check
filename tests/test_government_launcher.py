"""Configured launch routes use existing ledgers without changing their state."""
from __future__ import annotations

from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from test_temporal_assurance_web import HAS_API, TemporalWebFixture


@unittest.skipUnless(HAS_API and importlib.util.find_spec("uvicorn") is not None,
                     "console server dependencies unavailable")
class GovernmentLauncherTests(TemporalWebFixture, unittest.TestCase):
    def test_unconfigured_temporal_service_never_creates_a_registry(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.api import create_app
        from model_release_assurance.temporal_assurance import web

        self.assertEqual(web.DEFAULT_ROOT, Path(".local/temporal-assurance"))
        self.assertFalse(web.DEFAULT_ROOT.is_absolute())
        absent = Path(self.temp.name) / "absent-temporal-default"
        with patch.object(web, "DEFAULT_ROOT", absent):
            with TestClient(create_app(Path(self.temp.name) / "synthetic-default",
                                       repository=self.repo)) as client:
                self.assertEqual(client.get("/api/temporal/study").json()["status"], "unavailable")
                self.assertEqual(client.get("/api/temporal/operator").json()["status"], "unavailable")
        self.assertFalse(absent.exists())

    def test_custom_roots_serve_the_existing_study_and_operator_without_spending(self):
        from fastapi.testclient import TestClient
        from model_release_assurance.export_poc.cli import main
        from model_release_assurance.temporal_assurance.pipeline import has_schema

        original = self.store.ledger()
        inventory = (self.operator / "workflow.json").read_bytes()
        # The inherited fixture is a temporary toy registry, never the ACS study.
        with patch("model_release_assurance.temporal_assurance.web.DEFAULT_ROOT", self.run / "missing"), \
                patch("uvicorn.run") as run:
            result = main(["serve", "--data", str(self.operator.parent / "configured-synthetic"),
                           "--repository", str(self.repo), "--temporal-run", str(self.run),
                           "--temporal-operator", str(self.operator)])
        self.assertEqual(result, 0)
        with TestClient(run.call_args.args[0]) as client:
            self.assertEqual(client.get("/api/temporal/study").json()["status"], "verified")
            status = client.get("/api/temporal/operator").json()
            self.assertEqual(status["status"], "available")
            self.assertEqual(status["summary"]["revision"], 0)
            self.assertEqual(status["summary"]["committed_releases"], 0)
            self.assertEqual(status["summary"]["maximum_spent_epsilon"], 0)
            self.assertEqual(status["models"][0]["model_id"], "step-01-model-D1")
            self.assertEqual(client.get("/api/temporal/downloads/unprepared").status_code, 404)
        self.assertEqual(self.store.ledger(), original)
        self.assertEqual((self.operator / "workflow.json").read_bytes(), inventory)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertFalse(has_schema(db))


if __name__ == "__main__":
    unittest.main()
