from __future__ import annotations

import inspect
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import Field

from .analyzers import (
    AttackAnalyzer,
    AttackBatteryAnalyzer,
    ControlledInferenceAnalyzer,
    DpAnalyzer,
    LlmCanaryAnalyzer,
    LlmWatermarkAnalyzer,
    PopulationAnalyzer,
    TreeLinkageAnalyzer,
)
from .analyzers.base import Analyzer
from .integrity import sha256_file
from .models import (
    AnalyzerInput,
    EvidenceRecord,
    ReleaseContract,
    StrictModel,
    ThreatContract,
)


class ServiceTransport(StrEnum):
    IN_PROCESS = "in_process"
    MCP = "mcp"


class AnalyzerServiceDescriptor(StrictModel):
    """Stable discovery metadata for a replaceable analyzer service."""

    service_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    service_version: str = Field(min_length=1, max_length=128)
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_kind: str = Field(min_length=1, max_length=128)
    transport: ServiceTransport
    mcp_tool: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    can_clear: bool
    can_block: bool
    deterministic: bool = True


class AnalyzerService(Protocol):
    descriptor: AnalyzerServiceDescriptor

    def supports(self, value: AnalyzerInput) -> bool: ...

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]: ...


class LocalAnalyzerService:
    """Compatibility adapter that gives an in-process analyzer a service boundary."""

    def __init__(
        self,
        analyzer: Analyzer,
        *,
        version: str = "1.0.0",
        can_clear: bool | None = None,
        can_block: bool | None = None,
    ):
        source_path = inspect.getsourcefile(analyzer.__class__)
        if source_path is None:
            raise ValueError("analyzer implementation must have a hashable source file")
        declared_can_clear = analyzer.can_clear
        declared_can_block = analyzer.can_block
        effective_can_clear = declared_can_clear if can_clear is None else can_clear
        effective_can_block = declared_can_block if can_block is None else can_block
        if effective_can_clear and not declared_can_clear:
            raise ValueError("analyzer service cannot widen the analyzer's clearance capability")
        if effective_can_block and not declared_can_block:
            raise ValueError("analyzer service cannot widen the analyzer's blocking capability")
        self.analyzer = analyzer
        self.descriptor = AnalyzerServiceDescriptor(
            service_id=f"mra.analyzer.{analyzer.name}",
            service_version=version,
            implementation_sha256=sha256_file(Path(source_path)),
            input_kind=analyzer.name,
            transport=ServiceTransport.IN_PROCESS,
            mcp_tool=f"analyze_{analyzer.name}",
            can_clear=effective_can_clear,
            can_block=effective_can_block,
        )

    def supports(self, value: AnalyzerInput) -> bool:
        return self.analyzer.supports(value)

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        return self.analyzer.analyze(release, threat, value)


McpInvoke = Callable[[str, dict[str, Any]], dict[str, Any]]


class McpAnalyzerService:
    """Transport adapter for a future MCP analyzer without coupling the core to an SDK."""

    def __init__(self, descriptor: AnalyzerServiceDescriptor, invoke: McpInvoke):
        if descriptor.transport is not ServiceTransport.MCP:
            raise ValueError("MCP analyzer descriptor must use the mcp transport")
        self.descriptor = descriptor
        self._invoke = invoke

    def supports(self, value: AnalyzerInput) -> bool:
        return value.analyzer == self.descriptor.input_kind

    def analyze(
        self,
        release: ReleaseContract,
        threat: ThreatContract,
        value: AnalyzerInput,
    ) -> tuple[EvidenceRecord, ...]:
        response = self._invoke(self.descriptor.mcp_tool, {
            "contract_version": "2.0",
            "release": release.model_dump(mode="json", exclude_none=False),
            "threat": threat.model_dump(mode="json", exclude_none=False),
            "analyzer_input": value.model_dump(mode="json", exclude_none=False),
        })
        if response.get("contract_version") != "2.0":
            raise ValueError("MCP analyzer returned an unsupported contract version")
        raw_records = response.get("evidence")
        if not isinstance(raw_records, list) or not raw_records:
            raise ValueError("MCP analyzer returned no evidence records")
        return tuple(EvidenceRecord.model_validate(item) for item in raw_records)


class AnalyzerServiceRegistry:
    """Fail-closed routing for independently replaceable analyzer services."""

    def __init__(self, services: tuple[AnalyzerService, ...]):
        if not services:
            raise ValueError("at least one analyzer service is required")
        service_ids = [service.descriptor.service_id for service in services]
        input_kinds = [service.descriptor.input_kind for service in services]
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("analyzer service identifiers must be unique")
        if len(input_kinds) != len(set(input_kinds)):
            raise ValueError("analyzer service input kinds must be unique")
        self.services = services

    def resolve(self, value: AnalyzerInput) -> AnalyzerService:
        matches = [service for service in self.services if service.supports(value)]
        if len(matches) != 1:
            raise ValueError(f"expected one analyzer service for {value.analyzer}, found {len(matches)}")
        return matches[0]

    def describe(self) -> tuple[AnalyzerServiceDescriptor, ...]:
        return tuple(service.descriptor for service in self.services)


def default_analyzer_service_registry() -> AnalyzerServiceRegistry:
    return AnalyzerServiceRegistry((
        LocalAnalyzerService(TreeLinkageAnalyzer()),
        LocalAnalyzerService(DpAnalyzer()),
        LocalAnalyzerService(AttackAnalyzer()),
        LocalAnalyzerService(AttackBatteryAnalyzer()),
        LocalAnalyzerService(ControlledInferenceAnalyzer()),
        LocalAnalyzerService(LlmWatermarkAnalyzer()),
        LocalAnalyzerService(LlmCanaryAnalyzer()),
        LocalAnalyzerService(PopulationAnalyzer()),
    ))
