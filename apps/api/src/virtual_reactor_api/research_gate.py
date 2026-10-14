"""Compact, auditable search decision for reaction generation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from virtual_reactor_api.agent_models import (
    ReactionGenerationRequest,
    ResearchGateDecision,
)
from virtual_reactor_api.evaluation_recorder import (
    record_evaluation_event,
    serialize_for_evaluation,
)
from virtual_reactor_api.research_query_planner import plan_research_queries


RESEARCH_GATE_PROMPT = """你是虚拟反应器的检索决策器。只判断生成半定量单反应配置是否需要联网检索，不生成配置。
只有在反应身份、目标产物、路线和条件都已有可靠用户资料或直接证据，且用户明确只要概念趋势时才可 skip。
只要请求包含两个以上具体化学物料、药物/中间体名称、工艺优化词或收率/纯度数据，必须先检索确认，
不得因为反应类型看似常见而跳过。
身份歧义、陌生体系、文献/专利/精确参数请求、定量热模型、重大危险、放大或真实设备结论必须 targeted 或 required。
不得把模型记忆表述为外部证据。输出严格符合 ResearchGateDecision。"""


class StructuredResearchGate:
    """Use one compact model call and conservative deterministic upgrades."""

    def __init__(self, model: Any) -> None:
        self._model = model.with_structured_output(
            ResearchGateDecision,
            include_raw=True,
        )

    async def decide(
        self,
        request: ReactionGenerationRequest,
    ) -> ResearchGateDecision:
        messages = [
            {"role": "system", "content": RESEARCH_GATE_PROMPT},
            {"role": "user", "content": request.prompt_description()},
        ]
        record_evaluation_event("research_gate_request", {"messages": messages})
        try:
            result = await self._model.ainvoke(messages)
            record_evaluation_event(
                "research_gate_raw_result",
                {"result": serialize_for_evaluation(result)},
            )
            decision = _parse_decision(result)
        except Exception as error:
            decision = _failure_fallback(request, error)
        return _apply_required_upgrades(request, decision)


def _parse_decision(result: Any) -> ResearchGateDecision:
    if isinstance(result, ResearchGateDecision):
        return result
    if isinstance(result, Mapping) and "parsed" in result:
        parsed = result.get("parsed")
        if parsed is None:
            raise ValueError("research gate structured parsing failed")
        return parsed if isinstance(parsed, ResearchGateDecision) else ResearchGateDecision.model_validate(parsed)
    return ResearchGateDecision.model_validate(result)


def _failure_fallback(
    request: ReactionGenerationRequest,
    error: Exception,
) -> ResearchGateDecision:
    record_evaluation_event(
        "research_gate_failed",
        {"errorType": type(error).__name__, "fallbackDecision": "targeted"},
    )
    return ResearchGateDecision(
        difficulty="advanced",
        searchDecision="targeted",
        reasonCodes=["gate_failure_fallback"],
        reason="检索判断暂时失败，采用保守的有限检索策略。",
        evidenceTargets=["反应身份、关键条件与模拟参数"],
        scholarBudget=1,
        webBudget=1,
    )


def _apply_required_upgrades(
    request: ReactionGenerationRequest,
    decision: ResearchGateDecision,
) -> ResearchGateDecision:
    text = request.prompt_description().casefold()
    triggers = {
        "explicit_evidence_request": ("文献", "论文", "专利", "doi", "sds", "来源"),
        "precision_request": ("精确动力学", "活化能", "反应焓", "定量热模型"),
        "scale_or_equipment_request": ("放大", "中试", "工业", "真实设备"),
        "high_risk_request": ("爆炸", "高压", "剧毒", "失控", "强放热"),
        "process_optimization_request": ("工艺", "优化", "收率", "纯度", "杂质", "投料比", "当量", "催化剂", "加入顺序", "反应时间", "反应温度", "中间体"),
    }
    matched = [code for code, words in triggers.items() if any(word in text for word in words)]
    # A concrete multi-material request is not a safe teaching-only shortcut:
    # identity and route must be checked before the model chooses a mechanism.
    material_markers = ("苯甲醛", "乙酰乙酸", "硝基", "中间体", "哌啶", "甲氧乙酯")
    if sum(marker in text for marker in material_markers) >= 2:
        matched.append("concrete_multi_material_system")
    planned_queries = plan_research_queries(request.prompt_description())
    if decision.searchDecision != "skip" and planned_queries:
        return decision.model_copy(update={"evidenceTargets": [*decision.evidenceTargets, *planned_queries]})
    if not matched:
        return decision
    must_be_required = any(code in matched for code in ("concrete_multi_material_system", "process_optimization_request"))
    upgraded = decision.model_copy(
        update={
            "difficulty": "advanced",
            "searchDecision": "required" if must_be_required else "targeted",
            "reasonCodes": [*decision.reasonCodes, *matched],
            "reason": "请求包含必须外部核实的证据、精度、安全、放大或设备要求。",
            "evidenceTargets": ["用户明确要求核实的关键科学或工程信息", *planned_queries],
            "scholarBudget": max(2 if must_be_required else 1, decision.scholarBudget),
            "webBudget": max(2 if must_be_required else 1, decision.webBudget),
        }
    )
    record_evaluation_event(
        "research_gate_overridden",
        {"original": decision, "upgraded": upgraded, "reasonCodes": matched},
    )
    return upgraded
