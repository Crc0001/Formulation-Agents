"""Production Deep Agents, model, and web-search adapters."""

from __future__ import annotations

import copy
import json
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from .safe_filesystem import ResearchFilesystemBackend
from deepagents.middleware import FilesystemMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import ToolException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from virtual_reactor_api.agent_models import (
    CandidatePreflightReport,
    GeneratorDecision,
    GeneratorOutput,
    ReactionGenerationRequest,
    ResearchGateDecision,
)
from virtual_reactor_api.agent_context import AgentRunContext
from virtual_reactor_api.agent_audit import AgentAuditMiddleware
from virtual_reactor_api.agent_preflight import validate_candidate_preflight
from virtual_reactor_api.patent_reader import create_google_patent_reader_tool
from virtual_reactor_api.agent_prompts import (
    FRONTEND_CAPABILITIES,
    GENERATOR_SYSTEM_PROMPT,
)
from virtual_reactor_api.agent_service import ReactionAgentService
from virtual_reactor_api.research_gate import StructuredResearchGate
from virtual_reactor_api.evaluation_store import EvaluationStore
from virtual_reactor_api.evaluation_recorder import (
    record_evaluation_event,
    serialize_for_evaluation,
)
from virtual_reactor_api.contracts import ReactionSimulationConfig
from virtual_reactor_api.scholar_search import (
    create_serpapi_google_tool,
    create_serpapi_patents_tool,
    create_serpapi_scholar_tool,
)
from virtual_reactor_api.scientific.tools import (
    ScientificToolRuntime,
    create_scientific_tools,
)
from virtual_reactor_api.scientific.contracts import (
    IdentifiabilityInput,
    ModelComparisonInput,
)
from virtual_reactor_api.scientific.identifiability import (
    assess_parameter_identifiability,
)
from virtual_reactor_api.scientific.report import (
    ScientificCompletionIssue,
    collect_scientific_completion_issues,
)
from virtual_reactor_api.scientific.workspace import WorkspaceManager

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_AGENT_CONFIG_PATH = PROJECT_ROOT / "config" / "agent.local.toml"
DEFAULT_EVALUATION_DATABASE_PATH = PROJECT_ROOT / "data" / "evaluations.sqlite3"
DEFAULT_WORKSPACE_RUNS_PATH = PROJECT_ROOT / "workspace" / "runs"


class AgentConfigurationError(RuntimeError):
    """Raised when required external model or search settings are absent."""


class AgentRuntimeError(RuntimeError):
    """Raised when an external agent returns an invalid runtime result."""


@dataclass(frozen=True, slots=True)
class AgentRuntimeSettings:
    generatorModel: str
    generatorApiKey: str = field(repr=False)
    generatorBaseUrl: str | None
    serpapiApiKey: str = field(repr=False)
    serpapiCredentialSource: Literal["environment", "config_file"]
    searchMaxResults: int | None = None
    evaluationDatabasePath: Path = field(
        default_factory=lambda: DEFAULT_EVALUATION_DATABASE_PATH
    )
    workspaceRunsPath: Path = field(
        default_factory=lambda: DEFAULT_WORKSPACE_RUNS_PATH
    )
    maximumAgentIterations: int = 56
    maximumModelTurns: int = 28

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
    ) -> "AgentRuntimeSettings":
        return cls.from_sources(os.environ if env is None else env)

    @classmethod
    def from_sources(
        cls,
        env: Mapping[str, str],
        *,
        config_path: Path | None = DEFAULT_AGENT_CONFIG_PATH,
    ) -> "AgentRuntimeSettings":
        file_values = _load_agent_config(config_path)
        resolved = {
            "generator_model": env.get("VR_AGENT_MODEL")
            or _nested_text(file_values, "generator", "model"),
            "generator_api_key": env.get("VR_AGENT_API_KEY")
            or _nested_text(file_values, "generator", "api_key"),
            "generator_base_url": env.get("VR_AGENT_BASE_URL")
            or _nested_text(file_values, "generator", "base_url"),
            "serpapi_api_key": env.get("SERPAPI_API_KEY")
            or _nested_text(file_values, "search", "serpapi_api_key"),
            "search_max_results": env.get("VR_SEARCH_MAX_RESULTS")
            or _nested_value(file_values, "search", "max_results"),
            "evaluation_database_path": env.get("VR_EVALUATION_DB")
            or _nested_text(file_values, "evaluation", "database_path"),
            "workspace_runs_path": env.get("VR_WORKSPACE_RUNS_PATH")
            or _nested_text(file_values, "workspace", "runs_path"),
            "maximum_agent_iterations": env.get("VR_AGENT_MAX_ITERATIONS"),
            "maximum_model_turns": env.get("VR_AGENT_MAX_MODEL_TURNS"),
        }
        required_labels = {
            "generator_model": "生成模型 model",
            "generator_api_key": "生成模型 api_key",
            "serpapi_api_key": "检索服务 serpapi_api_key",
        }
        missing = [
            label for key, label in required_labels.items() if not resolved[key]
        ]
        if missing:
            raise AgentConfigurationError(
                "智能体配置缺少：" + "、".join(missing)
            )
        return cls(
            generatorModel=_openai_model_spec(resolved["generator_model"]),
            generatorApiKey=resolved["generator_api_key"] or "",
            generatorBaseUrl=resolved["generator_base_url"] or None,
            serpapiApiKey=resolved["serpapi_api_key"] or "",
            serpapiCredentialSource=(
                "environment" if env.get("SERPAPI_API_KEY") else "config_file"
            ),
            searchMaxResults=_optional_positive_int(
                resolved["search_max_results"],
                label="search.max_results",
            ),
            evaluationDatabasePath=Path(
                resolved["evaluation_database_path"]
                or DEFAULT_EVALUATION_DATABASE_PATH
            ),
            workspaceRunsPath=Path(
                resolved["workspace_runs_path"] or DEFAULT_WORKSPACE_RUNS_PATH
            ),
            maximumAgentIterations=_optional_positive_int(
                resolved["maximum_agent_iterations"],
                label="VR_AGENT_MAX_ITERATIONS",
            )
            or 56,
            maximumModelTurns=_optional_positive_int(
                resolved["maximum_model_turns"],
                label="VR_AGENT_MAX_MODEL_TURNS",
            )
            or 28,
        )


def _load_agent_config(path: Path | None) -> Mapping[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        with path.open("rb") as config_file:
            return tomllib.load(config_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise AgentConfigurationError(
            f"无法读取智能体配置文件：{path}"
        ) from error


def _nested_text(
    values: Mapping[str, Any],
    section: str,
    key: str,
) -> str | None:
    section_values = values.get(section)
    if not isinstance(section_values, Mapping):
        return None
    value = section_values.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _nested_value(
    values: Mapping[str, Any],
    section: str,
    key: str,
) -> Any:
    section_values = values.get(section)
    return section_values.get(key) if isinstance(section_values, Mapping) else None


def _optional_positive_int(value: Any, *, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AgentConfigurationError(f"{label} 必须是正整数")
    if isinstance(value, float) and not value.is_integer():
        raise AgentConfigurationError(f"{label} 必须是正整数")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise AgentConfigurationError(f"{label} 必须是正整数") from error
    if parsed <= 0:
        raise AgentConfigurationError(f"{label} 必须是正整数")
    return parsed


def resolve_evaluation_database_path(
    env: Mapping[str, str] | None = None,
    *,
    config_path: Path | None = DEFAULT_AGENT_CONFIG_PATH,
) -> Path:
    """Resolve evaluation storage without requiring model credentials."""

    active_env = os.environ if env is None else env
    file_values = _load_agent_config(config_path)
    configured = active_env.get("VR_EVALUATION_DB") or _nested_text(
        file_values,
        "evaluation",
        "database_path",
    )
    return Path(configured) if configured else DEFAULT_EVALUATION_DATABASE_PATH


def _openai_model_spec(value: str | None) -> str:
    if value is None:
        return ""
    return value if ":" in value else f"openai:{value}"


class DeepAgentGraph(Protocol):
    async def ainvoke(
        self,
        input_value: dict[str, Any],
        config: dict[str, Any],
    ) -> Mapping[str, Any]: ...


def build_deep_agent(
    *,
    model: Any,
    tools: list[Any],
    workspace: Any,
    middleware: list[Any],
    agent_factory: Any = create_deep_agent,
    system_prompt: str = GENERATOR_SYSTEM_PROMPT,
    output_schema: Any = GeneratorDecision,
) -> DeepAgentGraph:
    """Build one run-scoped generator graph without execution or delegation."""

    backend = ResearchFilesystemBackend(
        root_dir=workspace.root,
        virtual_mode=True,
    )
    filesystem_middleware = FilesystemMiddleware(
        backend=backend,
        tools=["ls", "read_file", "write_file", "edit_file", "glob", "grep"],
    )
    return agent_factory(
        model=model,
        tools=tools,
        backend=backend,
        system_prompt=system_prompt,
        subagents=[],
        middleware=[filesystem_middleware, *middleware],
        response_format=ToolStrategy(output_schema, handle_errors=True),
        checkpointer=InMemorySaver(
            serde=JsonPlusSerializer(pickle_fallback=True),
        ),
        name="virtual-reactor-generator",
    )


def register_single_agent_profile(
    model_spec: str,
    *,
    registrar: Any = register_harness_profile,
) -> None:
    """Disable Deep Agents' automatically-added general-purpose subagent."""

    registrar(
        model_spec,
        HarnessProfile(
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)
        ),
    )


class DeepAgentReactionGenerator:
    """Adapt a structured Deep Agents graph to the generator protocol."""

    def __init__(
        self,
        model: Any,
        search_tools: list[Any],
        *,
        agent_factory: Any = create_deep_agent,
        maximum_iterations: int = 56,
        maximum_model_turns: int = 28,
        middleware_factory: Any | None = None,
    ) -> None:
        self._model = model
        self._search_tools = list(search_tools)
        self._agent_factory = agent_factory
        self._maximum_iterations = maximum_iterations
        self._middleware_factory = middleware_factory or (
            lambda context: [
                AgentAuditMiddleware(
                    max_model_turns=maximum_model_turns,
                    retry_delay_seconds=10,
                    progress_reporter=context.progressReporter,
                )
            ]
        )

    async def generate(
        self,
        request: ReactionGenerationRequest,
        *,
        research_gate: ResearchGateDecision | None = None,
        run_context: AgentRunContext,
    ) -> GeneratorOutput:
        message = _generator_message(
            request,
            research_gate=research_gate,
            prior_research_evidence=run_context.priorResearchEvidence,
        )
        model_content = _generator_content(request, message)
        thread_id = run_context.runId
        record_evaluation_event(
            "generator_request",
            {
                "systemPrompt": GENERATOR_SYSTEM_PROMPT,
                "userMessage": message,
                "userContent": model_content,
                "threadId": thread_id,
            },
        )
        try:
            active_search_tools = (
                []
                if research_gate is not None
                and research_gate.searchDecision == "skip"
                else self._search_tools
            )
            scientific_tools = create_scientific_tools(
                ScientificToolRuntime(
                    ledger=run_context.ledger,
                    limits=run_context.toolLimits,
                )
            )
            active_agent = build_deep_agent(
                model=self._model,
                tools=[*active_search_tools, *scientific_tools],
                workspace=run_context.workspace,
                middleware=list(self._middleware_factory(run_context)),
                agent_factory=self._agent_factory,
            )
            agent_config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": self._maximum_iterations,
            }
            decision = await _invoke_decision(
                active_agent,
                model_content,
                agent_config,
                repair_model=self._model,
            )
        except ToolException as error:
            raise AgentRuntimeError(str(error)) from error
        except AgentRuntimeError:
            raise
        except Exception as error:
            raise AgentRuntimeError("生成模型调用失败，请稍后重试。") from error

        if decision.kind == "candidate":
            candidate = _require_candidate(decision)
            _derive_identifiability_from_model_comparison(run_context)
            issues = collect_scientific_completion_issues(
                run_context.ledger,
                candidate.scientificRationale,
            )
            record_evaluation_event(
                "scientific_completion_check",
                {
                    "attempt": 0,
                    "issues": [item.as_payload() for item in issues],
                },
            )
            if not issues:
                return await self._revise_technical_issues(
                    active_agent, agent_config, candidate
                )

            record_evaluation_event(
                "scientific_recovery_started",
                {
                    "attempt": 1,
                    "issues": [item.as_payload() for item in issues],
                },
            )
            try:
                recovery = await _invoke_decision(
                    active_agent,
                    _scientific_recovery_message(candidate, issues),
                    agent_config,
                    repair_model=self._model,
                )
            except ToolException as error:
                _record_scientific_recovery_failure(issues, "tool_exception")
                raise AgentRuntimeError(str(error)) from error
            except AgentRuntimeError:
                _record_scientific_recovery_failure(issues, "invalid_decision")
                raise
            except Exception as error:
                _record_scientific_recovery_failure(issues, "model_invocation")
                raise AgentRuntimeError("科学补算模型调用失败，请稍后重试。") from error
            if recovery.kind != "candidate":
                _record_scientific_recovery_failure(issues, "non_candidate")
                raise AgentRuntimeError("科学补算未返回候选配置。")
            candidate = _require_candidate(recovery)
            issues = collect_scientific_completion_issues(
                run_context.ledger,
                candidate.scientificRationale,
            )
            event_type = (
                "scientific_recovery_completed"
                if not issues
                else "scientific_recovery_failed"
            )
            record_evaluation_event(
                event_type,
                {
                    "attempt": 1,
                    "issues": [item.as_payload() for item in issues],
                },
            )
            if issues:
                names = "、".join(item.toolName for item in issues)
                raise AgentRuntimeError(f"科学补算后仍未完成：{names}")
            return await self._revise_technical_issues(
                active_agent, agent_config, candidate
            )
        if decision.clarification is None:
            raise AgentRuntimeError("生成模型缺少澄清问题。")
        return decision.clarification


    async def _revise_technical_issues(
        self,
        active_agent: DeepAgentGraph,
        agent_config: dict[str, Any],
        candidate: Any,
    ) -> Any:
        """诊断不可执行时给模型一轮技术修订机会；失败则原样交付候选。"""
        report = validate_candidate_preflight(candidate)
        if report.executable is not False:
            return candidate
        deterministically_repaired = _remove_unused_decorative_controls(
            candidate, report
        )
        if deterministically_repaired is not None:
            repaired_report = validate_candidate_preflight(
                deterministically_repaired
            )
            if repaired_report.executable is not False:
                record_evaluation_event(
                    "technical_revision_completed",
                    {
                        "attempt": 0,
                        "strategy": "remove_unused_decorative_controls",
                        "executable": True,
                        "issueCount": 0,
                    },
                )
                return deterministically_repaired
        record_evaluation_event(
            "technical_revision_started",
            {
                "attempt": 1,
                "issues": [item.model_dump(mode="json") for item in report.issues],
            },
        )
        try:
            revision = await _invoke_decision(
                active_agent,
                _technical_revision_message(candidate, report),
                agent_config,
                repair_model=self._model,
            )
        except Exception:
            record_evaluation_event(
                "technical_revision_failed",
                {"attempt": 1, "failureKind": "invocation"},
            )
            return candidate
        if revision.kind != "candidate":
            record_evaluation_event(
                "technical_revision_failed",
                {"attempt": 1, "failureKind": "non_candidate"},
            )
            return candidate
        try:
            revised = _require_candidate(revision)
        except AgentRuntimeError:
            record_evaluation_event(
                "technical_revision_failed",
                {"attempt": 1, "failureKind": "invalid_candidate"},
            )
            return candidate
        revised_report = validate_candidate_preflight(revised)
        improved = revised_report.executable is not False
        record_evaluation_event(
            "technical_revision_completed" if improved else "technical_revision_skipped",
            {
                "attempt": 1,
                "executable": revised_report.executable,
                "issueCount": len(revised_report.issues),
            },
        )
        return revised if improved else candidate


def _remove_unused_decorative_controls(
    candidate: Any,
    report: CandidatePreflightReport,
) -> Any | None:
    """Remove controls proven unused; never infer or rewrite a scientific link."""
    blocking_issues = [
        issue for issue in report.issues if issue.severity == "block"
    ]
    if not blocking_issues or any(
        issue.code != "unused_control" for issue in blocking_issues
    ):
        return None
    indexes: set[int] = set()
    for issue in blocking_issues:
        parts = issue.fieldPath.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["config", "controls"]:
            return None
        try:
            indexes.add(int(parts[2]))
        except ValueError:
            return None
    payload = candidate.model_dump(mode="json")
    controls = payload.get("config", {}).get("controls")
    if not isinstance(controls, list) or any(
        index < 0 or index >= len(controls) for index in indexes
    ):
        return None
    payload["config"]["controls"] = [
        control for index, control in enumerate(controls) if index not in indexes
    ]
    try:
        return candidate.__class__.model_validate(payload)
    except Exception:
        return None


def _record_scientific_recovery_failure(
    issues: list[ScientificCompletionIssue],
    failure_kind: str,
) -> None:
    record_evaluation_event(
        "scientific_recovery_failed",
        {
            "attempt": 1,
            "failureKind": failure_kind,
            "issues": [item.as_payload() for item in issues],
        },
    )


def _parse_tool_args_text(args_text: str) -> dict[str, Any] | None:
    """解析工具调用参数文本；模型偶发输出破损 JSON，失败时用 json-repair 兜底。"""
    try:
        parsed = json.loads(args_text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json

            repaired = repair_json(args_text)
            parsed = json.loads(repaired) if isinstance(repaired, str) else repaired
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _last_decision_args_text(messages: list[Any]) -> str:
    """取最后一条 AI 消息中 GeneratorDecision 调用的原始参数文本。"""
    for message in reversed(messages):
        for block in list(getattr(message, "content", None) or []):
            if (
                isinstance(block, dict)
                and block.get("name") == "GeneratorDecision"
                and block.get("partial_json")
            ):
                return str(block["partial_json"])
        for chunk in list(getattr(message, "tool_call_chunks", None) or []):
            if chunk.get("name") == "GeneratorDecision" and chunk.get("args"):
                return str(chunk["args"])
    return ""


def _decision_tool_payload(call: Any) -> dict[str, Any] | None:
    """从单个工具调用（含流式 partial_json 形态）提取已解析的参数。"""
    if not isinstance(call, dict) or call.get("name") != "GeneratorDecision":
        return None
    args = call.get("args")
    if isinstance(args, dict):
        return args
    if isinstance(args, str) and args.strip():
        return _parse_tool_args_text(args)
    return None


def _extract_decision_from_messages(
    messages: list[Any],
) -> GeneratorDecision | None:
    """流式聚合偶发丢失工具参数导致 structured_response 为空；从消息兜底解析。"""
    for message in reversed(messages):
        payloads: list[dict[str, Any] | None] = []
        for call in list(getattr(message, "tool_calls", None) or []):
            payloads.append(_decision_tool_payload(call))
        for block in list(getattr(message, "content", None) or []):
            if isinstance(block, dict) and block.get("name") == "GeneratorDecision":
                args_text = block.get("partial_json") or ""
                if isinstance(args_text, str) and args_text.strip():
                    merged = _parse_tool_args_text(args_text) or {}
                else:
                    merged = {}
                merged.update(block.get("input") or {})
                payloads.append(merged or None)
        for chunk in list(getattr(message, "tool_call_chunks", None) or []):
            payloads.append(_decision_tool_payload(chunk))
        for payload in payloads:
            if isinstance(payload, dict):
                try:
                    return GeneratorDecision.model_validate(payload)
                except Exception:
                    continue
    return None


_REPAIR_SYSTEM_PROMPT = (
    "你是 JSON 结构修复器。用户会给出一份未通过 schema 校验的 JSON、错误清单与目标 schema。"
    "请修复所有错误（补缺失字段、删除多余字段、纠正字段位置、类型与语法），"
    "不改动任何科学内容语义，仅输出修复后的完整 JSON，不要输出其他文字。"
)


def _decision_schema_text() -> str:
    return json.dumps(
        GeneratorDecision.model_json_schema(), ensure_ascii=False, indent=1
    )


async def _repair_decision_with_model(
    repair_model: Any,
    raw_args_text: str,
    validation_errors: list[str],
) -> dict[str, Any] | None:
    """把校验失败的原始 JSON 与错误清单发回模型做一次聚焦修复。"""
    message = (
        f"目标 schema：\n{_decision_schema_text()}\n\n"
        "校验错误清单：\n"
        + "\n".join(f"- {item}" for item in validation_errors[:40])
        + "\n\n原始 JSON：\n"
        + raw_args_text
    )
    try:
        response = await repair_model.ainvoke(
            [
                {"role": "system", "content": _REPAIR_SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        text = _message_text(response)
        payload = _parse_tool_args_text(_strip_json_fence(text))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _decision_validation_errors(payload: dict[str, Any]) -> list[str]:
    try:
        GeneratorDecision.model_validate(payload)
        return []
    except Exception as error:
        return [
            f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('type')} "
            f"(input={str(item.get('input'))[:60]})"
            for item in error.errors()  # type: ignore[attr-defined]
        ]


def _repair_unambiguous_decision_shape(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Repair representation-only conflicts without changing scientific values."""
    repaired = copy.deepcopy(payload)
    fixes: list[str] = []
    candidate = repaired.get("candidate")
    if not isinstance(candidate, dict):
        return repaired, fixes

    synthesis = candidate.get("researchSynthesis")
    if isinstance(synthesis, dict):
        for source_index, source in enumerate(synthesis.get("sources") or []):
            if (
                isinstance(source, dict)
                and source.get("sourceType") == "patent_example"
                and source.get("accessLevel") in {"abstract", "snippet"}
            ):
                source["sourceType"] = "patent_document"
                fixes.append(
                    f"candidate.researchSynthesis.sources.{source_index}.sourceType"
                )

    for index, block in enumerate(candidate.get("assistantContent") or []):
        if not isinstance(block, dict) or block.get("kind") != "reaction_equation":
            continue
        equation = block.get("equation")
        if isinstance(equation, dict) and equation.get("role") != "explanatory":
            equation["role"] = "explanatory"
            fixes.append(f"candidate.assistantContent.{index}.equation.role")

    config = candidate.get("config")
    if not isinstance(config, dict):
        return repaired, fixes
    control_ids = {
        item.get("id")
        for item in config.get("controls") or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for reaction_index, reaction in enumerate(config.get("reactions") or []):
        if not isinstance(reaction, dict):
            continue
        for modifier_index, modifier in enumerate(reaction.get("modifiers") or []):
            if not isinstance(modifier, dict):
                continue
            if (
                modifier.get("controlId") in control_ids
                and modifier.get("processVariableId") == "reactor_temperature"
            ):
                modifier.pop("processVariableId", None)
                fixes.append(
                    f"candidate.config.reactions.{reaction_index}.modifiers."
                    f"{modifier_index}.processVariableId"
                )
    for annotation_index, annotation in enumerate(config.get("annotations") or []):
        if not isinstance(annotation, dict):
            continue
        trigger = annotation.get("trigger")
        if (
            isinstance(trigger, dict)
            and trigger.get("kind") == "control_outside_recommended"
            and "value" not in trigger
        ):
            # The engine does not consult value for this trigger kind. Preserve
            # the stable wire schema with a neutral placeholder.
            trigger["value"] = 0
            fixes.append(
                f"candidate.config.annotations.{annotation_index}.trigger.value"
            )
    return repaired, fixes


async def _invoke_decision(
    agent: DeepAgentGraph,
    message: str | list[dict[str, Any]],
    config: dict[str, Any],
    *,
    repair_model: Any = None,
) -> GeneratorDecision:
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": message}]},
        config,
    )
    record_evaluation_event(
        "generator_raw_result",
        {"result": serialize_for_evaluation(result)},
    )
    raw_decision = result.get("structured_response")
    try:
        return (
            raw_decision
            if isinstance(raw_decision, GeneratorDecision)
            else GeneratorDecision.model_validate(raw_decision)
        )
    except Exception as error:
        raw_args_text = _last_decision_args_text(result.get("messages", []))
        fallback = _extract_decision_from_messages(result.get("messages", []))
        if fallback is not None:
            return fallback
        if raw_args_text:
            payload = _parse_tool_args_text(raw_args_text)
            if payload is not None:
                payload, deterministic_fixes = _repair_unambiguous_decision_shape(payload)
                try:
                    repaired_decision = GeneratorDecision.model_validate(payload)
                    record_evaluation_event(
                        "generator_decision_repaired",
                        {"attempt": 0, "fields": deterministic_fixes},
                    )
                    return repaired_decision
                except Exception:
                    pass
        if raw_args_text and repair_model is not None:
            payload = _parse_tool_args_text(raw_args_text)
            if payload is not None:
                payload, _ = _repair_unambiguous_decision_shape(payload)
            current_text = (
                json.dumps(payload, ensure_ascii=False)
                if payload is not None
                else raw_args_text
            )
            attempt = 0
            for attempt in range(1, 4):
                errors = (
                    _decision_validation_errors(payload)
                    if payload is not None
                    else ["JSON 语法无效，无法解析"]
                )
                if not errors:
                    break
                repaired = await _repair_decision_with_model(
                    repair_model, current_text, errors
                )
                if repaired is None:
                    break
                payload = repaired
                current_text = json.dumps(repaired, ensure_ascii=False)
            if payload is not None:
                try:
                    repaired_decision = GeneratorDecision.model_validate(payload)
                    record_evaluation_event(
                        "generator_decision_repaired",
                        {"attempt": attempt},
                    )
                    return repaired_decision
                except Exception:
                    pass
        raise AgentRuntimeError("生成模型未返回合法的结构化决策。") from error


def _require_candidate(decision: GeneratorDecision):
    if decision.candidate is None:
        raise AgentRuntimeError("生成模型缺少候选配置。")
    if decision.candidate.scientificRationale is None:
        raise AgentRuntimeError("生成模型缺少可审计的科学推理摘要。")
    return decision.candidate


def _technical_revision_message(
    candidate: Any,
    report: CandidatePreflightReport,
) -> str:
    payload = {
        "kind": "technical_revision",
        "attempt": 1,
        "remainingAttempts": 0,
        "issues": [item.model_dump(mode="json") for item in report.issues],
        "candidate": candidate.model_dump(mode="json"),
        "instructions": [
            "只修复问题清单指出的问题；普通结构问题不得更改科学语义。",
            "若问题代码是 selected_route_lacks_direct_conditions、missing_route_outcome_assessment 或 missing_route_purification_assessment，必须调用专利/文献工具补齐直接证据，并仅据真实工具结果更新研究整理、证据和所选条件；不得伪造来源。",
            "调整计量系数或来源当量映射时必须保持化学合理性与当量守恒。",
            "返回修复后的完整 CandidateReactionConfig。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _scientific_recovery_message(
    candidate: Any,
    issues: list[ScientificCompletionIssue],
) -> str:
    payload = {
        "kind": "scientific_completion_recovery",
        "attempt": 1,
        "remainingAttempts": 0,
        "issues": [item.as_payload() for item in issues],
        "candidate": candidate.model_dump(mode="json"),
        "instructions": [
            "实际调用每个问题指定的科学工具，不得只声称已经检查。",
            "输入无效时根据回执警告修正工具参数。",
            "证据不足时保留不确定性，不得伪造数据或拟合结果。",
            "完成工具调用后返回一个完整的 CandidateReactionConfig。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _derive_identifiability_from_model_comparison(
    run_context: AgentRunContext,
) -> None:
    """Reuse an existing fit request instead of asking the model to copy it again.

    Model comparison already receives the candidate models and observations.  When
    the agent omitted the separate identifiability call, run the deterministic
    checker with those exact inputs.  A missing sensitivity matrix deliberately
    produces ``insufficient_data``; that is an honest accepted conclusion and does
    not justify discarding the literature synthesis or candidate configuration.
    """
    receipts = run_context.ledger.receipts
    if any(
        receipt.toolName == "assess_parameter_identifiability"
        for receipt in receipts
    ):
        return
    comparison_receipt = next(
        (
            receipt
            for receipt in reversed(receipts)
            if receipt.toolName == "fit_and_compare_models"
            and receipt.status in {"success", "insufficient_data"}
        ),
        None,
    )
    if comparison_receipt is None:
        return
    try:
        comparison = ModelComparisonInput.model_validate(
            comparison_receipt.normalizedInput
        )
        selected_id = comparison_receipt.result.get("selectedModelId")
        model = next(
            (
                item
                for item in comparison.models
                if item.modelId == selected_id
            ),
            comparison.models[0],
        )
        request = IdentifiabilityInput(
            model=model,
            observations=comparison.observations,
            sensitivityMatrix=None,
        )
    except (ValueError, TypeError, KeyError):
        return

    call = run_context.ledger.start(
        "assess_parameter_identifiability",
        request.model_dump(mode="json"),
    )
    result = assess_parameter_identifiability(request)
    run_context.ledger.complete(
        call,
        status=result.status,
        result=result.model_dump(mode="json"),
        warnings=list(result.warnings),
        assumptions=["复用同次模型比较工具的候选模型与观测；未推造灵敏度矩阵。"],
        applicability=["仅适用于同次模型比较提交的候选模型与观测。"],
    )


def create_reaction_agent_service(
    settings: AgentRuntimeSettings | None = None,
) -> ReactionAgentService:
    """Create the production single-pass generator and search integrations."""

    active = settings or AgentRuntimeSettings.from_env()
    register_single_agent_profile(active.generatorModel)
    generator_model = _create_model(
        active.generatorModel,
        active.generatorApiKey,
        active.generatorBaseUrl,
    )
    search_tools = [
        create_serpapi_scholar_tool(
            active.serpapiApiKey,
            max_results=active.searchMaxResults,
        ),
        create_serpapi_google_tool(
            active.serpapiApiKey,
            max_results=active.searchMaxResults,
        ),
        create_serpapi_patents_tool(
            active.serpapiApiKey,
            max_results=active.searchMaxResults,
        ),
        create_google_patent_reader_tool(active.serpapiApiKey),
    ]
    generator = DeepAgentReactionGenerator(
        generator_model,
        search_tools,
        maximum_iterations=active.maximumAgentIterations,
        maximum_model_turns=active.maximumModelTurns,
    )
    return ReactionAgentService(
        generator,
        evaluation_store=EvaluationStore(active.evaluationDatabasePath),
        workspace_manager=WorkspaceManager(active.workspaceRunsPath),
        frontend_capabilities=FRONTEND_CAPABILITIES,
        evaluation_metadata={
            "generatorModel": active.generatorModel,
            "searchProviders": [
                "serpapi:google_scholar",
                "serpapi:google",
                "serpapi:google_patents",
                "google_patents:document_reader",
            ],
            "serpapiCredentialSource": active.serpapiCredentialSource,
            "searchMaxResults": active.searchMaxResults,
            "constraintPolicyVersion": "1.0.0",
            "reactionConfigSchemaVersion": "1.5.0",
            "candidatePreflightRuleVersion": "1.5.0",
            "pathwayCompletenessPolicyVersion": "1.0.0",
            "maximumAgentIterations": active.maximumAgentIterations,
            "maximumModelTurns": active.maximumModelTurns,
            "reviewPolicy": "disabled_user_judgment",
            "agentFramework": "deepagents",
            "scientificToolProtocolVersion": "1.0.0",
        },
        research_gate=StructuredResearchGate(generator_model),
    )

def _create_model(
    model_name: str,
    api_key: str,
    base_url: str | None,
) -> BaseChatModel:
    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "temperature": 0,
        # 默认 None 为无限等待；断流的请求会永远挂住，交给重试中间件处理更稳妥。
        "timeout": 600.0,
        # 客户端默认 4096 会截断最终候选配置的大 JSON 工具调用参数。
        "max_tokens": 32768,
        # ainvoke 默认走非流式 POST，大响应单连接挂 10 分钟以上易被网关掐断；
        # 流式模式下分块持续到达，连接保活且断流能被读超时快速发现。
        "streaming": True,
    }
    if base_url is not None:
        kwargs["base_url"] = base_url
    if model_name.startswith("openai:"):
        # langchain_openai 另有 stream_chunk_timeout（默认 120 秒，可用
        # LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S 覆盖）：它测量"解析后分块之间的间隔"，
        # SSE keepalive 不会重置它。默认 120 秒会在长思考/长结构化输出前抢先抛
        # StreamChunkTimeoutError，使 research_limits.model_wait_seconds 给 GLM 的 300 秒
        # 和 Astra 的 600 秒外层窗口完全失效（实测 102 批次两项均在约 120 秒静默后失败）。
        # 这里把它放到外层窗口之上，只作为真正静默死连接的后备，不再抢先中断。
        # 仅 OpenAI 兼容路径设置：其他提供方没有该参数，传入只会被塞进 model_kwargs。
        kwargs["stream_chunk_timeout"] = 900.0
    if model_name in ("openai:gpt-6-astra", "gpt-6-astra"):
        # Astra tool calling uses Responses; sampling temperature is unsupported.
        kwargs.pop("temperature", None)
        kwargs.update(use_responses_api=True, reasoning={"effort": "medium"}, store=False)
        from urllib.parse import urlsplit
        if base_url and (urlsplit(base_url).hostname or '').endswith('.ts.net'):
            # Tailnet gateway must bypass OS proxy auto-discovery; TLS verification stays on.
            import httpx
            kwargs.update(http_client=httpx.Client(trust_env=False, timeout=600),
                          http_async_client=httpx.AsyncClient(trust_env=False, timeout=600))
    if model_name.startswith('openai:glm-') and base_url:
        from urllib.parse import urlsplit
        if urlsplit(base_url).hostname == 'open.bigmodel.cn':
            # Windows proxy discovery caused reproducible TLS EOFs for this endpoint.
            # Keep certificate verification enabled and other providers unchanged.
            import httpx
            kwargs.update(http_client=httpx.Client(trust_env=False, timeout=600),
                          http_async_client=httpx.AsyncClient(trust_env=False, timeout=600))
    return init_chat_model(model_name, **kwargs)


def _generator_message(
    request: ReactionGenerationRequest,
    *,
    research_gate: ResearchGateDecision | None = None,
    prior_research_evidence: tuple[dict[str, Any], ...] = (),
) -> str:
    user_request = request.model_dump(mode="json", exclude={"images"})
    user_request["description"] = request.prompt_description()
    user_request["images"] = [
        {"filename": image.filename, "mediaType": image.mediaType}
        for image in request.images
    ]
    payload = {
        "userRequest": user_request,
        "frontendCapabilities": FRONTEND_CAPABILITIES,
        "researchGate": None
        if research_gate is None
        else research_gate.model_dump(mode="json"),
        "priorResearchEvidence": list(prior_research_evidence),
        "reactionSimulationConfigSchema": (
            ReactionSimulationConfig.model_json_schema(mode="validation")
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


def _generator_content(
    request: ReactionGenerationRequest,
    message: str,
) -> str | list[dict[str, Any]]:
    if not request.images:
        return message
    return [
        {"type": "text", "text": message},
        *[
            {
                "type": "image_url",
                "image_url": {"url": image.dataUrl, "detail": "high"},
            }
            for image in request.images
        ],
    ]
