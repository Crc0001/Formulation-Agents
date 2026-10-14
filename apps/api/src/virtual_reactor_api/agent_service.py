"""Provider-independent single-pass reaction generation orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Mapping, Protocol
from uuid import UUID, uuid4

from virtual_reactor_api.agent_context import AgentRunContext
from virtual_reactor_api.agent_models import (
    AgentGenerationResult,
    CandidatePreflightReport,
    CandidateReactionConfig,
    ClarificationRequest,
    EligibilityIssue,
    GeneratorOutput,
    ReactionGenerationRequest,
    ResearchGateDecision,
)
from virtual_reactor_api.agent_preflight import validate_candidate_preflight
from virtual_reactor_api.evaluation_recorder import (
    EvaluationRecorder,
    record_evaluation_event,
    reset_current_recorder,
    set_current_recorder,
)
from virtual_reactor_api.evaluation_store import EvaluationStore
from virtual_reactor_api.scientific.ledger import ScientificRunLedger
from virtual_reactor_api.scientific.report import (
    assemble_scientific_report,
    validate_scientific_bottom_lines,
)
from virtual_reactor_api.scientific.tools import ScientificToolLimits
from virtual_reactor_api.scientific.workspace import WorkspaceManager


DEFAULT_WORKSPACE_RUNS_ROOT = (
    Path(__file__).resolve().parents[4] / "workspace" / "runs"
)


class ReactionConfigGenerator(Protocol):
    async def generate(
        self,
        request: ReactionGenerationRequest,
        *,
        research_gate: ResearchGateDecision | None = None,
        run_context: AgentRunContext,
    ) -> GeneratorOutput: ...


class ReactionResearchGate(Protocol):
    async def decide(
        self,
        request: ReactionGenerationRequest,
    ) -> ResearchGateDecision: ...


class ReactionAgentService:
    """Generate one candidate without reviewer approval or revision rounds."""

    def __init__(
        self,
        generator: ReactionConfigGenerator,
        *,
        evaluation_store: EvaluationStore | None = None,
        evaluation_metadata: Mapping[str, Any] | None = None,
        research_gate: ReactionResearchGate | None = None,
        workspace_manager: WorkspaceManager | None = None,
        frontend_capabilities: Mapping[str, Any] | None = None,
        scientific_tool_limits: ScientificToolLimits | None = None,
    ) -> None:
        self._generator = generator
        self._evaluation_store = evaluation_store
        self._evaluation_metadata = dict(evaluation_metadata or {})
        self._research_gate = research_gate
        self._workspace_manager = workspace_manager or WorkspaceManager(
            DEFAULT_WORKSPACE_RUNS_ROOT
        )
        self._frontend_capabilities = dict(frontend_capabilities or {})
        self._scientific_tool_limits = scientific_tool_limits or ScientificToolLimits()

    async def generate(
        self,
        request: ReactionGenerationRequest,
        on_progress: Callable[[Literal["generating"], str, int], Awaitable[None]]
        | None = None,
    ) -> AgentGenerationResult:
        recorder = (
            None
            if self._evaluation_store is None
            else EvaluationRecorder.start(
                self._evaluation_store,
                request,
                {
                    **self._evaluation_metadata,
                    "reviewPolicy": "disabled_user_judgment",
                    "candidatePreflightRuleVersion": "1.5.0",
                },
            )
        )
        token = None if recorder is None else set_current_recorder(recorder)
        run_id = recorder.run_id if recorder is not None else str(uuid4())
        orchestration_started = perf_counter()
        try:
            workspace = self._workspace_manager.create(run_id)
            workspace.write_json("input/request.json", request)
            workspace.write_json(
                "input/frontend-capabilities.json", self._frontend_capabilities
            )
            record_evaluation_event(
                "workspace_created",
                {"workspaceId": run_id, "relativePath": f"workspace/runs/{run_id}"},
            )
            gate_started = perf_counter()
            gate = await self._decide_research(request)
            record_evaluation_event(
                "research_gate_decision",
                {"decision": gate, "durationMs": _duration_ms(gate_started)},
            )
            record_evaluation_event("generation_started", {"generationCount": 1})
            await _report(on_progress, "正在检索资料并生成反应配置。")
            generation_started = perf_counter()
            ledger = ScientificRunLedger(
                workspace,
                random_seed=UUID(run_id).int % (2**31),
            )
            prior_research = self._load_prior_research_evidence(
                request,
                exclude_run_id=run_id,
            )
            workspace.write_json("input/prior-research-evidence.json", prior_research)
            record_evaluation_event(
                "prior_research_evidence_projected",
                {
                    "conversationId": request.conversationId,
                    "sourceRunCount": len(prior_research),
                    "projections": prior_research,
                },
            )

            async def report_generation_progress(message: str) -> None:
                await _report(on_progress, message)

            run_context = AgentRunContext(
                runId=run_id,
                workspace=workspace,
                conversationId=request.conversationId,
                researchGate=gate,
                randomSeed=ledger.random_seed,
                toolLimits=self._scientific_tool_limits,
                ledger=ledger,
                progressReporter=(
                    report_generation_progress
                    if on_progress is not None
                    else None
                ),
                priorResearchEvidence=tuple(prior_research),
            )
            output = await self._generator.generate(
                request,
                research_gate=gate,
                run_context=run_context,
            )
            record_evaluation_event(
                "generator_output",
                {
                    "generationCount": 1,
                    "output": output,
                    "durationMs": _duration_ms(generation_started),
                },
            )

            if isinstance(output, ClarificationRequest):
                result = AgentGenerationResult(
                    status="needs_clarification",
                    candidate=None,
                    diagnostics=None,
                    researchGate=gate,
                    runId=run_id,
                    clarificationQuestion=output.question,
                    scientificAnalysis=None,
                )
            else:
                candidate, diagnostics = _normalize_and_diagnose(output)
                record_evaluation_event(
                    "candidate_technical_diagnostics",
                    {"candidate": candidate, "diagnostics": diagnostics},
                )
                scientific_analysis = None
                if candidate.scientificRationale is not None:
                    try:
                        scientific_analysis = _assemble_scientific_analysis(
                            run_id, candidate, ledger
                        )
                    except ValueError as error:
                        record_evaluation_event(
                            "scientific_report_assembly_failed",
                            {"message": str(error)},
                        )
                        diagnostics = diagnostics.model_copy(
                            update={
                                "executable": False,
                                "issues": [
                                    *diagnostics.issues,
                                    EligibilityIssue(
                                        code="invalid_scientific_report_references",
                                        fieldPath="/candidate/scientificRationale/citedToolCallIds",
                                        scope="simulation",
                                        severity="block",
                                        message=(
                                            "科学报告引用与当前运行不一致，候选内容已保留但不能载入模拟。"
                                        ),
                                    ),
                                ],
                            }
                        )
                if scientific_analysis is not None:
                    record_evaluation_event(
                        "scientific_report_assembled",
                        {"report": scientific_analysis},
                    )
                result = AgentGenerationResult(
                    status="generated",
                    candidate=candidate,
                    diagnostics=diagnostics,
                    researchGate=gate,
                    runId=run_id,
                    clarificationQuestion=None,
                    scientificAnalysis=scientific_analysis,
                )
                workspace.write_json("output/candidate.json", candidate)
                workspace.write_json("output/diagnostics.json", diagnostics)

            record_evaluation_event(
                "orchestration_completed",
                {"durationMs": _duration_ms(orchestration_started)},
            )
            if recorder is not None:
                recorder.complete(result)
            return result
        except BaseException as error:
            if recorder is not None:
                recorder.fail(error)
            raise
        finally:
            if token is not None:
                reset_current_recorder(token)

    def _load_prior_research_evidence(
        self,
        request: ReactionGenerationRequest,
        *,
        exclude_run_id: str,
    ) -> list[dict[str, Any]]:
        if self._evaluation_store is None:
            return []
        page = self._evaluation_store.list_runs(limit=100)
        same_conversation = [
            item
            for item in page.items
            if request.conversationId is not None
            and item.request.get("conversationId") == request.conversationId
        ]
        same_description = [
            item
            for item in page.items
            if str(item.request.get("description") or "").strip()
            == request.description.strip()
            and item not in same_conversation
        ]
        projections: list[dict[str, Any]] = []
        for summary in [*same_conversation, *same_description]:
            if summary.runId == exclude_run_id:
                continue
            detail = self._evaluation_store.get_run(summary.runId)
            final_result = None if detail is None else detail.finalResult
            candidate = (
                final_result.get("candidate")
                if isinstance(final_result, Mapping)
                else None
            )
            synthesis = (
                candidate.get("researchSynthesis")
                if isinstance(candidate, Mapping)
                else None
            )
            if not isinstance(synthesis, Mapping):
                continue
            projections.append(
                {
                    "sourceRunId": summary.runId,
                    "matchKind": (
                        "conversation"
                        if summary in same_conversation
                        else "exact_description"
                    ),
                    "completedAt": None
                    if summary.completedAt is None
                    else summary.completedAt.isoformat(),
                    "researchSynthesis": dict(synthesis),
                }
            )
            if len(projections) >= 3:
                break
        return projections

    async def _decide_research(
        self,
        request: ReactionGenerationRequest,
    ) -> ResearchGateDecision:
        if self._research_gate is not None:
            return await self._research_gate.decide(request)
        return ResearchGateDecision(
            difficulty="advanced",
            searchDecision="required",
            reasonCodes=["default_research_policy"],
            reason="未配置独立检索闸门，生成智能体按完整证据流程检索。",
            evidenceTargets=["反应身份、机理、条件与关键模拟参数"],
            scholarBudget=5,
            webBudget=3,
        )


def _normalize_and_diagnose(
    candidate: CandidateReactionConfig,
) -> tuple[CandidateReactionConfig, CandidatePreflightReport]:
    return candidate, validate_candidate_preflight(candidate)


async def _report(
    callback: Callable[[Literal["generating"], str, int], Awaitable[None]] | None,
    message: str,
) -> None:
    if callback is not None:
        await callback("generating", message, 0)


def _duration_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


def _assemble_scientific_analysis(run_id, candidate, ledger):
    validate_scientific_bottom_lines(ledger)
    return assemble_scientific_report(
        run_id,
        candidate.scientificRationale,
        ledger,
    )
