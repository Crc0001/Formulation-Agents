"""Assemble public scientific reports from registered tool receipts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from virtual_reactor_api.agent_models import (
    CandidateModelAssessment,
    IdentifiabilitySummary,
    ParameterSourceSummary,
    ScientificAnalysisReport,
    ScientificFinding,
    ScientificRationale,
)
from virtual_reactor_api.scientific.ledger import ScientificRunLedger
from virtual_reactor_api.scientific.contracts import ScientificToolStatus


@dataclass(frozen=True, slots=True)
class ScientificCompletionIssue:
    toolName: str
    kind: Literal["missing", "non_success", "invalid_reference"]
    status: ScientificToolStatus | None
    message: str
    warnings: tuple[str, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        return {
            "toolName": self.toolName,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "warnings": list(self.warnings),
        }


def collect_scientific_completion_issues(
    ledger: ScientificRunLedger,
    rationale: ScientificRationale | None = None,
) -> list[ScientificCompletionIssue]:
    latest = {receipt.toolName: receipt for receipt in ledger.receipts}
    issues: list[ScientificCompletionIssue] = []
    for tool_name in (
        "validate_quantities_and_units",
        "analyze_stoichiometry",
        "simulate_candidate_kinetics",
    ):
        receipt = latest.get(tool_name)
        if receipt is None:
            issues.append(
                ScientificCompletionIssue(
                    toolName=tool_name,
                    kind="missing",
                    status=None,
                    message=f"缺少必需科学工具回执：{tool_name}",
                )
            )
        elif receipt.status != "success":
            issues.append(
                ScientificCompletionIssue(
                    toolName=tool_name,
                    kind="non_success",
                    status=receipt.status,
                    message=f"必需科学工具未成功：{tool_name}",
                    warnings=tuple(receipt.warnings),
                )
            )

    identifiability = latest.get("assess_parameter_identifiability")
    if identifiability is None:
        issues.append(
            ScientificCompletionIssue(
                toolName="assess_parameter_identifiability",
                kind="missing",
                status=None,
                message="缺少参数可辨识性回执。",
            )
        )
    elif identifiability.status in {"invalid_input", "numerical_failure"}:
        issues.append(
            ScientificCompletionIssue(
                toolName="assess_parameter_identifiability",
                kind="non_success",
                status=identifiability.status,
                message="参数可辨识性检查存在技术错误。",
                warnings=tuple(identifiability.warnings),
            )
        )
    if rationale is not None:
        receipt_ids = {item.toolCallId for item in ledger.receipts}
        cited_ids = set(rationale.citedToolCallIds)
        for comparison in rationale.candidateComparisons:
            cited_ids.update(comparison.toolCallIds)
        for parameter in rationale.parameterSources:
            cited_ids.update(parameter.toolCallIds)
        missing_ids = sorted(cited_ids - receipt_ids)
        if missing_ids:
            issues.append(
                ScientificCompletionIssue(
                    toolName="scientific_rationale",
                    kind="invalid_reference",
                    status=None,
                    message=(
                        "科学依据引用了不属于当前运行的工具回执；必须删除历史回执标识或改为当前回执："
                        + "、".join(missing_ids)
                    ),
                )
            )
    return issues


def validate_scientific_bottom_lines(ledger: ScientificRunLedger) -> None:
    issues = collect_scientific_completion_issues(ledger)
    if issues:
        raise ValueError("; ".join(issue.message for issue in issues))


def _hamming_distance(left: str, right: str) -> int | None:
    """等长字符串的不同字符数；长度不同返回 None。"""
    if len(left) != len(right):
        return None
    return sum(1 for a, b in zip(left, right) if a != b)


def _resolve_cited_tool_call_id(
    cited: str, receipt_by_id: dict[str, Any]
) -> str:
    """归一模型引用的收据 ID：精确 > 唯一前缀 > 唯一近邻（≤2 字符差异）。"""
    if cited in receipt_by_id:
        return cited
    prefix_matches = [full for full in receipt_by_id if full.startswith(cited)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    # 生成模型偶发抄错个别字符（如 8b4e 写成 8c4e）；UUID 间距远大于 2，
    # 唯一近邻才归一，歧义时保持原样交给缺失校验拦截。
    neighbors = [
        full
        for full in receipt_by_id
        if (distance := _hamming_distance(cited, full)) is not None
        and distance <= 2
    ]
    if len(neighbors) == 1:
        return neighbors[0]
    return cited


def _normalize_cited_tool_call_ids(
    rationale: ScientificRationale, receipt_by_id: dict[str, Any]
) -> None:
    """生成模型偶尔只引用收据 ID 的前缀（如 tool-a0b3b6dc）；归一后再校验。"""
    rationale.citedToolCallIds = [
        _resolve_cited_tool_call_id(item, receipt_by_id)
        for item in rationale.citedToolCallIds
    ]
    for comparison in rationale.candidateComparisons:
        comparison.toolCallIds = [
            _resolve_cited_tool_call_id(item, receipt_by_id)
            for item in comparison.toolCallIds
        ]
    for parameter in rationale.parameterSources:
        parameter.toolCallIds = [
            _resolve_cited_tool_call_id(item, receipt_by_id)
            for item in parameter.toolCallIds
        ]


def assemble_scientific_report(
    run_id: str,
    rationale: ScientificRationale,
    ledger: ScientificRunLedger,
) -> ScientificAnalysisReport:
    receipt_by_id = {item.toolCallId: item for item in ledger.receipts}
    _normalize_cited_tool_call_ids(rationale, receipt_by_id)
    missing = sorted(set(rationale.citedToolCallIds) - set(receipt_by_id))
    for comparison in rationale.candidateComparisons:
        missing.extend(
            item for item in comparison.toolCallIds if item not in receipt_by_id
        )
    for parameter in rationale.parameterSources:
        missing.extend(item for item in parameter.toolCallIds if item not in receipt_by_id)
    if missing:
        raise ValueError(
            "scientific rationale references missing tool receipts: "
            + ", ".join(sorted(set(missing)))
        )
    parameter_sources = [
        ParameterSourceSummary(
            **item.model_dump(),
            supported=_parameter_is_supported(item, receipt_by_id),
        )
        for item in rationale.parameterSources
    ]
    unsupported_fitted = [
        item.parameterId
        for item in parameter_sources
        if item.basis == "fitted" and not item.supported
    ]
    if unsupported_fitted:
        raise ValueError(
            "fitted parameter claims lack a successful identifiable fit receipt: "
            + ", ".join(unsupported_fitted)
        )
    receipts = list(ledger.receipts)
    return ScientificAnalysisReport(
        workspaceId=run_id,
        selectedModelId=rationale.selectedModelId,
        identitySummary=_findings(receipts, "inspect_chemical_identity"),
        unitSummary=_findings(receipts, "validate_quantities_and_units"),
        balanceSummary=_findings(receipts, "analyze_stoichiometry"),
        candidateModels=_candidate_models(rationale, receipt_by_id),
        identifiability=_identifiability(receipts),
        parameterSources=parameter_sources,
        numericalQuality=[
            *_findings(receipts, "simulate_candidate_kinetics"),
            *_findings(receipts, "fit_and_compare_models"),
        ],
        toolReceipts=receipts,
        warnings=list(
            dict.fromkeys(
                warning
                for receipt in receipts
                for warning in receipt.warnings
            )
        ),
        applicability=list(
            dict.fromkeys(
                item
                for receipt in receipts
                for item in receipt.applicability
            )
        ),
    )


def _findings(receipts: list, tool_name: str) -> list[ScientificFinding]:
    findings: list[ScientificFinding] = []
    for receipt in receipts:
        if receipt.toolName != tool_name:
            continue
        subjects = _subjects(receipt.result)
        if not subjects:
            subjects = [(tool_name, _summary(receipt.result, receipt.warnings))]
        findings.extend(
            ScientificFinding(
                status=receipt.status,
                subjectId=subject,
                summary=summary,
                toolCallId=receipt.toolCallId,
            )
            for subject, summary in subjects
        )
    return findings


def _subjects(result: dict[str, Any]) -> list[tuple[str, str]]:
    for key, id_key in (
        ("species", "speciesId"),
        ("quantities", "quantityId"),
        ("reactions", "reactionId"),
        ("models", "modelId"),
    ):
        collection = result.get(key)
        if isinstance(collection, list):
            return [
                (
                    str(item.get(id_key) or key),
                    _summary(item, []),
                )
                for item in collection
                if isinstance(item, dict)
            ]
    return []


def _summary(value: dict[str, Any], warnings: list[str]) -> str:
    for key in ("message", "summary", "verdict", "derivedFormula", "error"):
        item = value.get(key)
        if item is not None and str(item).strip():
            return str(item)
    if warnings:
        return warnings[0]
    return "工具已返回结构化结果。"


def _candidate_models(
    rationale: ScientificRationale,
    receipt_by_id: dict[str, Any],
) -> list[CandidateModelAssessment]:
    assessments: list[CandidateModelAssessment] = []
    for comparison in rationale.candidateComparisons:
        metrics: dict[str, Any] = {}
        for receipt_id in comparison.toolCallIds:
            receipt = receipt_by_id[receipt_id]
            models = receipt.result.get("models")
            if not isinstance(models, list):
                continue
            match = next(
                (
                    item
                    for item in models
                    if isinstance(item, dict)
                    and item.get("modelId") == comparison.modelId
                ),
                None,
            )
            if match is not None:
                metrics.update(match)
        assessments.append(
            CandidateModelAssessment(
                modelId=comparison.modelId,
                selected=comparison.selected,
                reason=comparison.reason,
                metrics=metrics,
                toolCallIds=comparison.toolCallIds,
            )
        )
    return assessments


def _identifiability(receipts: list) -> IdentifiabilitySummary:
    for receipt in reversed(receipts):
        if receipt.toolName != "assess_parameter_identifiability":
            continue
        verdict = receipt.result.get("verdict", "unidentifiable")
        warnings = receipt.result.get("warnings") or receipt.warnings
        return IdentifiabilitySummary(
            status=receipt.status,
            verdict=verdict,
            details=(warnings[0] if warnings else f"参数判定：{verdict}"),
            unresolvedParameterIds=receipt.result.get(
                "unresolvedParameterIds", []
            ),
            toolCallId=receipt.toolCallId,
        )
    return IdentifiabilitySummary(
        status="insufficient_data",
        verdict="unidentifiable",
        details="本次运行未形成可辨识性工具回执。",
        unresolvedParameterIds=[],
        toolCallId=None,
    )


def _parameter_is_supported(parameter: Any, receipt_by_id: dict[str, Any]) -> bool:
    if parameter.basis != "fitted":
        return True
    for receipt_id in parameter.toolCallIds:
        receipt = receipt_by_id[receipt_id]
        if receipt.toolName != "fit_and_compare_models" or receipt.status != "success":
            continue
        for model in receipt.result.get("models", []):
            if not isinstance(model, dict):
                continue
            if (
                model.get("modelId") is not None
                and model.get("parameterBasisChangedToFitted") is True
                and parameter.parameterId in (model.get("parameters") or {})
            ):
                return True
    return False
