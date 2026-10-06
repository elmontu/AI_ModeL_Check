"""Lifecycle safeguards for the clone-and-run local government demo launcher."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("government_demo_launcher", ROOT / "scripts" / "start_demo.py")
assert SPEC is not None and SPEC.loader is not None
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


class GovernmentDemoLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="demo-launcher-tests-", dir=ROOT / ".local")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "demo environment"
        self.data = self.root / "demo data"

    def args(self, target: Path | None = None) -> list[str]:
        return ["--venv", str(target or self.target), "--data", str(self.data)]

    def invoke(self, arguments: list[str]) -> int:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return LAUNCHER.main(arguments)

    def fake_install(self, target: Path, wheelhouse: Path | None) -> None:
        self.assertFalse(target.exists(), "the installer must receive a fresh environment path")
        python = LAUNCHER.environment_python(target)
        python.parent.mkdir(parents=True)
        python.write_bytes(b"test environment Python placeholder\n")
        (target / "installation-diagnostic.txt").write_text("retained", encoding="utf-8")

    def ready_environment(self, target: Path | None = None) -> Path:
        target = target or self.target
        with patch.object(LAUNCHER, "install_environment", side_effect=self.fake_install), \
                patch.object(LAUNCHER, "validate_environment", return_value={"status": "verified"}), \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args(target) + ["--install-only"]), 0)
            launch.assert_not_called()
        marker = target / "mra-demo-install.json"
        self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), LAUNCHER.installation_binding())
        return marker

    def assert_refuses_existing(self, target: Path | None = None) -> None:
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "validate_environment") as validate, \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args(target)), 2)
            install.assert_not_called()
            validate.assert_not_called()
            launch.assert_not_called()

    def test_fresh_install_validates_before_publishing_marker_and_launching(self) -> None:
        order: list[str] = []
        marker = self.target / "mra-demo-install.json"

        def install(target: Path, wheelhouse: Path | None) -> None:
            order.append("install")
            self.fake_install(target, wheelhouse)

        def validate(target: Path) -> dict[str, str]:
            order.append("validate")
            self.assertEqual(target, self.target.resolve())
            self.assertFalse(marker.exists())
            return {"status": "verified"}

        def launch(target: Path, data: Path, port: int) -> int:
            order.append("launch")
            self.assertEqual(json.loads(marker.read_text(encoding="utf-8")), LAUNCHER.installation_binding())
            self.assertEqual((target, data, port), (self.target.resolve(), self.data.resolve(), 8765))
            return 0

        with patch.object(LAUNCHER, "install_environment", side_effect=install), \
                patch.object(LAUNCHER, "validate_environment", side_effect=validate), \
                patch.object(LAUNCHER, "launch_console", side_effect=launch):
            self.assertEqual(self.invoke(self.args()), 0)
        self.assertEqual(order, ["install", "validate", "launch"])

    def test_failed_install_retains_partial_environment_without_ready_marker(self) -> None:
        def fail(target: Path, wheelhouse: Path | None) -> None:
            self.fake_install(target, wheelhouse)
            raise subprocess.CalledProcessError(1, ["test-installer"])

        with patch.object(LAUNCHER, "install_environment", side_effect=fail), \
                patch.object(LAUNCHER, "validate_environment") as validate, \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args()), 2)
            validate.assert_not_called()
            launch.assert_not_called()
        self.assertEqual((self.target / "installation-diagnostic.txt").read_text(encoding="utf-8"), "retained")
        self.assertFalse((self.target / "mra-demo-install.json").exists())
        self.assert_refuses_existing()

    def test_failed_fresh_runtime_validation_does_not_publish_marker(self) -> None:
        with patch.object(LAUNCHER, "install_environment", side_effect=self.fake_install), \
                patch.object(LAUNCHER, "validate_environment", side_effect=ValueError("wrong runtime prefix")), \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args()), 2)
            launch.assert_not_called()
        self.assertTrue(self.target.is_dir())
        self.assertFalse((self.target / "mra-demo-install.json").exists())
        self.assert_refuses_existing()

    def test_input_drift_during_install_is_not_bound_as_success(self) -> None:
        initial = LAUNCHER.installation_binding()
        changed = copy.deepcopy(initial)
        first_input = next(iter(changed["inputs"]))
        changed["inputs"][first_input] = "0" * 64
        installed = False

        def install(target: Path, wheelhouse: Path | None) -> None:
            nonlocal installed
            self.fake_install(target, wheelhouse)
            installed = True

        with patch.object(LAUNCHER, "installation_binding", side_effect=lambda: changed if installed else initial), \
                patch.object(LAUNCHER, "install_environment", side_effect=install), \
                patch.object(LAUNCHER, "validate_environment", return_value={}), \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args()), 2)
            launch.assert_not_called()
        self.assertFalse((self.target / "mra-demo-install.json").exists())
        self.assertTrue((self.target / "installation-diagnostic.txt").is_file())

    def test_valid_repeat_launch_revalidates_without_reinstalling_or_overwriting(self) -> None:
        marker = self.ready_environment()
        before = marker.read_bytes()
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "validate_environment", return_value={}) as validate, \
                patch.object(LAUNCHER, "launch_console", return_value=0) as launch:
            self.assertEqual(self.invoke(self.args()), 0)
            install.assert_not_called()
            validate.assert_called_once_with(self.target.resolve())
            launch.assert_called_once_with(self.target.resolve(), self.data.resolve(), 8765)
        self.assertEqual(marker.read_bytes(), before)

    def test_unmarked_existing_directory_is_preserved_and_refused(self) -> None:
        self.target.mkdir()
        sentinel = self.target / "do-not-overwrite.txt"
        sentinel.write_bytes(b"existing environment\n")
        self.assert_refuses_existing()
        self.assertEqual(sentinel.read_bytes(), b"existing environment\n")
        self.assertEqual(list(self.target.iterdir()), [sentinel])

    def test_malformed_or_oversized_marker_never_triggers_repair(self) -> None:
        for index, content in enumerate((b"{not json", b"[]", b"{}", b" " * 16385)):
            with self.subTest(content=index):
                target = self.root / f"malformed-{index}"
                marker = self.ready_environment(target)
                marker.write_bytes(content)
                self.assert_refuses_existing(target)
                self.assertEqual(marker.read_bytes(), content)

    def test_wrong_checkout_or_changed_requirements_refuses_existing_environment(self) -> None:
        for field in ("repository", "inputs"):
            with self.subTest(field=field):
                target = self.root / f"stale-{field}"
                marker = self.ready_environment(target)
                value = json.loads(marker.read_text(encoding="utf-8"))
                if field == "repository":
                    value[field] = str(self.root / "another checkout")
                else:
                    value[field][next(iter(value[field]))] = "0" * 64
                marker.write_text(json.dumps(value), encoding="utf-8")
                before = marker.read_bytes()
                self.assert_refuses_existing(target)
                self.assertEqual(marker.read_bytes(), before)

    def test_marker_with_extra_fields_is_not_accepted(self) -> None:
        marker = self.ready_environment()
        value = json.loads(marker.read_text(encoding="utf-8"))
        value["unexpected"] = "not in the installation schema"
        marker.write_text(json.dumps(value), encoding="utf-8")
        self.assert_refuses_existing()
        self.assertIn("unexpected", json.loads(marker.read_text(encoding="utf-8")))

    def test_missing_environment_python_is_refused_without_reinstallation(self) -> None:
        marker = self.ready_environment()
        before = marker.read_bytes()
        LAUNCHER.environment_python(self.target).unlink()
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "launch_console") as launch, \
                patch.object(LAUNCHER.subprocess, "run") as subprocess_run:
            self.assertEqual(self.invoke(self.args()), 2)
            install.assert_not_called()
            launch.assert_not_called()
            subprocess_run.assert_not_called()
        self.assertEqual(marker.read_bytes(), before)

    def test_reused_runtime_validation_failure_does_not_reinstall_or_launch(self) -> None:
        marker = self.ready_environment()
        before = marker.read_bytes()
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "validate_environment", side_effect=ValueError("pip check failed")), \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args()), 2)
            install.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(marker.read_bytes(), before)

    def test_install_only_repeat_validates_and_does_not_start_service(self) -> None:
        marker = self.ready_environment()
        before = marker.read_bytes()
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "validate_environment", return_value={}) as validate, \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args() + ["--install-only"]), 0)
            install.assert_not_called()
            validate.assert_called_once_with(self.target.resolve())
            launch.assert_not_called()
        self.assertEqual(marker.read_bytes(), before)

    def test_invalid_ports_are_rejected_before_installation(self) -> None:
        for port in ("0", "65536", "-1", "not-a-port"):
            with self.subTest(port=port), \
                    patch.object(LAUNCHER, "install_environment") as install, \
                    patch.object(LAUNCHER, "validate_environment") as validate, \
                    patch.object(LAUNCHER, "launch_console") as launch, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    LAUNCHER.main(self.args() + ["--port", port])
                self.assertEqual(error.exception.code, 2)
                install.assert_not_called()
                validate.assert_not_called()
                launch.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_explicit_wheelhouse_and_port_are_forwarded_as_resolved_paths(self) -> None:
        wheelhouse = self.root / "approved wheels"
        wheelhouse.mkdir()
        with patch.object(LAUNCHER, "install_environment", side_effect=self.fake_install) as install, \
                patch.object(LAUNCHER, "validate_environment", return_value={}), \
                patch.object(LAUNCHER, "launch_console", return_value=0) as launch:
            self.assertEqual(self.invoke(self.args() + ["--wheelhouse", str(wheelhouse), "--port", "65535"]), 0)
            install.assert_called_once_with(self.target.resolve(), wheelhouse.resolve())
            launch.assert_called_once_with(self.target.resolve(), self.data.resolve(), 65535)
        missing = self.root / "missing wheels"
        fresh = self.root / "not created"
        with patch.object(LAUNCHER, "install_environment") as install, \
                patch.object(LAUNCHER, "launch_console") as launch:
            self.assertEqual(self.invoke(self.args(fresh) + ["--wheelhouse", str(missing)]), 2)
            install.assert_not_called()
            launch.assert_not_called()
        self.assertFalse(fresh.exists())

    def test_console_exit_status_and_interrupt_are_reported_without_reinstalling(self) -> None:
        marker = self.ready_environment()
        before = marker.read_bytes()
        for result, expected in ((7, 7), (KeyboardInterrupt(), 130)):
            with self.subTest(result=type(result).__name__), \
                    patch.object(LAUNCHER, "install_environment") as install, \
                    patch.object(LAUNCHER, "validate_environment", return_value={}), \
                    patch.object(LAUNCHER, "launch_console", side_effect=result if isinstance(result, BaseException) else None,
                                 return_value=result if isinstance(result, int) else 0):
                self.assertEqual(self.invoke(self.args()), expected)
                install.assert_not_called()
        self.assertEqual(marker.read_bytes(), before)


    def test_launch_uses_validated_python_without_ambient_import_paths(self) -> None:
        ambient = {"PYTHONHOME": str(self.root / "foreign Python"),
                   "PYTHONPATH": str(self.root / "foreign packages"),
                   "PYTHONSAFEPATH": "0", "MRA_TEST_SENTINEL": "retained"}
        with patch.dict(LAUNCHER.os.environ, ambient), \
                patch.object(LAUNCHER.subprocess, "Popen") as popen:
            console = popen.return_value
            console.wait.return_value = 0
            self.assertEqual(LAUNCHER.launch_console(self.target, self.data, 8765), 0)
            command = popen.call_args.args[0]
            environment = popen.call_args.kwargs["env"]
            self.assertEqual(command[0], str(LAUNCHER.environment_python(self.target)))
            self.assertIn("-I", command[:command.index("-m")])
            self.assertNotIn("PYTHONHOME", environment)
            self.assertNotIn("PYTHONPATH", environment)
            self.assertEqual(environment["PYTHONSAFEPATH"], "1")
            self.assertEqual(environment["MRA_TEST_SENTINEL"], "retained")
            self.assertEqual(LAUNCHER.os.environ["PYTHONHOME"], ambient["PYTHONHOME"])
            self.assertEqual(LAUNCHER.os.environ["PYTHONPATH"], ambient["PYTHONPATH"])
            console.wait.assert_called_once_with()
            console.__enter__.assert_not_called()

    def test_requirement_change_during_reuse_validation_stops_before_launch(self) -> None:
        checkout = self.root / "fixture checkout"
        for name in LAUNCHER.INPUTS:
            path = checkout / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        requirement = checkout / "requirements-console.txt"
        with patch.object(LAUNCHER, "ROOT", checkout):
            marker = self.ready_environment()
            before = marker.read_bytes()

            def validate(target: Path) -> dict[str, str]:
                requirement.write_bytes(requirement.read_bytes() + b"\n# validation-time fixture change\n")
                return {"status": "verified"}

            with patch.object(LAUNCHER, "install_environment") as install, \
                    patch.object(LAUNCHER, "validate_environment", side_effect=validate), \
                    patch.object(LAUNCHER, "launch_console") as launch:
                self.assertEqual(self.invoke(self.args()), 2)
                install.assert_not_called()
                launch.assert_not_called()
            self.assertEqual(marker.read_bytes(), before)
            self.assertIn(b"validation-time fixture change", requirement.read_bytes())

    def test_interrupted_shutdown_timeout_reports_unconfirmed_without_terminating_supervisor(self) -> None:
        diagnostic = io.StringIO()
        with patch.object(LAUNCHER.subprocess, "Popen") as popen, \
                redirect_stdout(io.StringIO()), redirect_stderr(diagnostic):
            console = popen.return_value
            console.wait.side_effect = [KeyboardInterrupt(), subprocess.TimeoutExpired("demo console", 30)]
            self.assertEqual(LAUNCHER.launch_console(self.target, self.data, 8765), 2)
            self.assertEqual(console.wait.call_args_list[0].args, ())
            self.assertEqual(console.wait.call_args_list[1].kwargs, {"timeout": 30})
            self.assertEqual(console.wait.call_count, 2)
            console.terminate.assert_not_called()
            console.kill.assert_not_called()
            console.__enter__.assert_not_called()
            console.__exit__.assert_not_called()
        self.assertIn("unconfirmed", diagnostic.getvalue().lower())

if __name__ == "__main__":
    unittest.main()
