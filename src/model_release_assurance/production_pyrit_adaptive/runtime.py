"""Adaptive scope declaration over unchanged pinned PyRIT dependency provenance."""
from __future__ import annotations
from ..production_pyrit import runtime as dependency_runtime
from ..production_adapters.contracts import canonical_bytes

LOCKED_VERSIONS = dependency_runtime.LOCKED_VERSIONS
DEPENDENCY_COMPONENT_SCOPE = dependency_runtime.COMPONENT_SCOPE
PyritRuntimeError = dependency_runtime.PyritRuntimeError
PyritRuntimeUnavailable = dependency_runtime.PyritRuntimeUnavailable
ADAPTIVE_COMPONENT_SCOPE = "RedTeamingAttack + in-memory SQLiteMemory + PromptNormalizer + case-sensitive SubStringScorer + bounded local adaptive attacker and objective target using shared model weights"


def expected_binding():
    return {"schema": "mra-pyrit-adaptive-runtime-binding/v1",
        "dependency_binding": dependency_runtime.expected_binding(),
        "component_scope": ADAPTIVE_COMPONENT_SCOPE,
        "shared_model": True,
        "identity_policy": "distinct attacker and target role identifiers and conversations; shared local model weights",
        "full_upstream_dependency_set": False, "fixture_only": True,
        "assessment_eligible": False, "authorization_eligible": False,
        "authorized": False, "production_authorized": False, "can_clear": False,
        "model_delivery": False, "hostile_code_isolated": False, "network_isolated": False,
        "filesystem_isolated": False, "resource_limits_verified": False}


def probe_runtime(expected_versions):
    observed = dependency_runtime.probe_runtime(expected_versions)
    if canonical_bytes(observed) != canonical_bytes(dependency_runtime.expected_binding()):
        raise PyritRuntimeError("Adaptive dependency provenance changed")
    binding = expected_binding()
    if canonical_bytes(binding["dependency_binding"]) != canonical_bytes(observed):
        raise PyritRuntimeError("Adaptive dependency binding changed")
    return binding
