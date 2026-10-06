"""Adaptive scope must preserve exact prior dependency provenance."""
from __future__ import annotations
import copy
import unittest
from unittest import mock
from model_release_assurance.production_pyrit import runtime as prior
from model_release_assurance.production_pyrit_adaptive import runtime


class AdaptiveRuntimeTests(unittest.TestCase):
    def test_new_scope_keeps_exact_dependency_provenance_and_shared_weights(self):
        observed = runtime.expected_binding()
        self.assertEqual(observed["schema"], "mra-pyrit-adaptive-runtime-binding/v1")
        self.assertEqual(observed["dependency_binding"], prior.expected_binding())
        self.assertEqual(observed["dependency_binding"]["component_scope"], runtime.DEPENDENCY_COMPONENT_SCOPE)
        self.assertIn("fixed scripted attacker", runtime.DEPENDENCY_COMPONENT_SCOPE)
        self.assertIn("adaptive attacker", observed["component_scope"])
        self.assertIs(observed["shared_model"], True)
        self.assertIs(observed["full_upstream_dependency_set"], False)
        for name in ("assessment_eligible", "authorization_eligible", "authorized", "production_authorized", "can_clear", "model_delivery", "hostile_code_isolated", "network_isolated", "filesystem_isolated", "resource_limits_verified"):
            self.assertIs(observed[name], False)

    def test_probe_delegates_exact_roster_and_integrity_validation(self):
        with mock.patch.object(prior, "probe_runtime", return_value=prior.expected_binding()) as probe:
            self.assertEqual(runtime.probe_runtime(runtime.LOCKED_VERSIONS), runtime.expected_binding())
        probe.assert_called_once_with(prior.LOCKED_VERSIONS)

    def test_missing_dependency_and_source_tamper_have_no_substitute(self):
        for failure in (prior.PyritRuntimeUnavailable("missing"), prior.PyritRuntimeError("tampered")):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(prior, "probe_runtime", side_effect=failure):
                with self.assertRaises(type(failure)): runtime.probe_runtime(runtime.LOCKED_VERSIONS)

    def test_dependency_boolean_cannot_be_restamped_as_integer(self):
        for name, value in (("fixture_only", 1), ("production_authorized", 0), ("full_upstream_dependency_set", 0)):
            changed = copy.deepcopy(prior.expected_binding()); changed[name] = value
            with self.subTest(name=name), mock.patch.object(prior, "probe_runtime", return_value=changed):
                with self.assertRaises(prior.PyritRuntimeError): runtime.probe_runtime(runtime.LOCKED_VERSIONS)

    def test_nested_scope_cannot_be_relabeled_as_full_adaptive_provenance(self):
        changed = copy.deepcopy(prior.expected_binding()); changed["component_scope"] = runtime.ADAPTIVE_COMPONENT_SCOPE
        with mock.patch.object(prior, "probe_runtime", return_value=changed):
            with self.assertRaises(prior.PyritRuntimeError): runtime.probe_runtime(runtime.LOCKED_VERSIONS)

    def test_returned_binding_mutations_do_not_change_old_provenance(self):
        changed = runtime.expected_binding()
        changed["dependency_binding"]["namespace_packages"].append("pyrit.unapproved")
        self.assertEqual(runtime.expected_binding()["dependency_binding"], prior.expected_binding())
        self.assertNotIn("pyrit.unapproved", prior.expected_binding()["namespace_packages"])


if __name__ == "__main__": unittest.main()
