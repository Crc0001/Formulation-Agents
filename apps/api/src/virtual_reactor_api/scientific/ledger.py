"""Run-scoped scientific tool receipts and audit mirroring."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from virtual_reactor_api.evaluation_recorder import (
    record_evaluation_event,
    serialize_for_evaluation,
)
from virtual_reactor_api.scientific.contracts import (
    ScientificToolReceipt,
    ScientificToolStatus,
)
from virtual_reactor_api.scientific.workspace import AgentRunWorkspace


@dataclass(frozen=True, slots=True)
class ScientificToolCall:
    toolCallId: str
    toolName: str
    normalizedInput: dict[str, Any]
    startedAt: float


class ScientificRunLedger:
    def __init__(self, workspace: AgentRunWorkspace, *, random_seed: int) -> None:
        self.workspace = workspace
        self.random_seed = random_seed
        self._receipts: list[ScientificToolReceipt] = []

    @property
    def receipts(self) -> tuple[ScientificToolReceipt, ...]:
        return tuple(self._receipts)

    def start(
        self, tool_name: str, normalized_input: dict[str, Any]
    ) -> ScientificToolCall:
        call = ScientificToolCall(
            toolCallId=f"tool-{uuid4()}",
            toolName=tool_name,
            normalizedInput=serialize_for_evaluation(normalized_input),
            startedAt=perf_counter(),
        )
        record_evaluation_event(
            "scientific_tool_started",
            {
                "toolCallId": call.toolCallId,
                "toolName": call.toolName,
                "normalizedInput": call.normalizedInput,
            },
        )
        return call

    def complete(
        self,
        call: ScientificToolCall,
        *,
        status: ScientificToolStatus,
        result: dict[str, Any],
        warnings: list[str],
        assumptions: list[str],
        applicability: list[str],
    ) -> ScientificToolReceipt:
        artifact_path = f"analysis/tool-receipts/{call.toolCallId}.json"
        receipt = ScientificToolReceipt(
            toolCallId=call.toolCallId,
            toolName=call.toolName,
            status=status,
            normalizedInput=call.normalizedInput,
            result=serialize_for_evaluation(result),
            warnings=warnings,
            assumptions=assumptions,
            applicability=applicability,
            durationMs=max(0, round((perf_counter() - call.startedAt) * 1000)),
            randomSeed=self.random_seed,
            libraryVersions=_library_versions(),
            artifactPath=artifact_path,
        )
        self.workspace.write_json(artifact_path, receipt)
        self.workspace.append_jsonl("analysis/tool-receipts.jsonl", receipt)
        self._receipts.append(receipt)
        event_type = {
            "success": "scientific_tool_completed",
            "insufficient_data": "scientific_tool_inconclusive",
            "invalid_input": "scientific_tool_failed",
            "numerical_failure": "scientific_tool_failed",
        }[status]
        record_evaluation_event(event_type, {"receipt": receipt})
        return receipt

    def fail(
        self,
        call: ScientificToolCall,
        message: str,
        *,
        status: Literal["invalid_input", "insufficient_data", "numerical_failure"],
    ) -> ScientificToolReceipt:
        return self.complete(
            call,
            status=status,
            result={},
            warnings=[message],
            assumptions=[],
            applicability=[],
        )


def _library_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in ("numpy", "scipy", "sympy", "pint", "rdkit"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result
