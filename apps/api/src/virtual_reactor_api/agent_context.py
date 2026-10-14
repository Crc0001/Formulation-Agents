"""Internal run context shared by orchestration and the Deep Agent runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from virtual_reactor_api.agent_models import ResearchGateDecision
from virtual_reactor_api.scientific.ledger import ScientificRunLedger
from virtual_reactor_api.scientific.tools import ScientificToolLimits
from virtual_reactor_api.scientific.workspace import AgentRunWorkspace


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    runId: str
    workspace: AgentRunWorkspace
    conversationId: str | None
    researchGate: ResearchGateDecision
    randomSeed: int
    toolLimits: ScientificToolLimits
    ledger: ScientificRunLedger
    progressReporter: Callable[[str], Awaitable[None]] | None = None
    priorResearchEvidence: tuple[dict[str, Any], ...] = ()
