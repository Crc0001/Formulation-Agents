"""Lossless JSONL and review-friendly Excel exports for agent evaluations."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable, Mapping
from typing import Any

import xlsxwriter

from virtual_reactor_api.evaluation_contracts import EvaluationRunDetail


_EXCEL_CELL_CHUNK = 30_000


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def export_jsonl(runs: Iterable[EvaluationRunDetail]) -> bytes:
    lines = [
        json.dumps(run.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        for run in runs
    ]
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def export_xlsx(runs: Iterable[EvaluationRunDetail]) -> bytes:
    run_list = list(runs)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title = workbook.add_format(
        {"bold": True, "font_color": "#FFFFFF", "bg_color": "#0F766E", "border": 1}
    )
    body = workbook.add_format({"valign": "top", "text_wrap": True, "border": 1})
    date = workbook.add_format(
        {"valign": "top", "num_format": "yyyy-mm-dd hh:mm:ss", "border": 1}
    )

    summary = _sheet(
        workbook,
        "任务总览",
        [18, 16, 21, 21, 42, 24, 24, 12, 36, 24, 20, 14, 20, 18,
         16, 16, 16, 16, 16, 16],
        title,
    )
    summary_headers = [
        "运行编号", "状态", "创建时间", "完成时间", "用户请求", "生成模型",
        "审核模型", "事件数", "错误", "模拟资格", "真实设备资格",
        "默认阻断数", "虚拟设备来源", "设备规则版本",
        "配置协议", "限制策略", "预检规则", "检索结果上限",
        "上下文物料数", "技术诊断数",
    ]
    _headers(summary, summary_headers, title)
    for row, run in enumerate(run_list, start=1):
        request_text = str(run.request.get("description") or _json(run.request))
        summary.write(row, 0, run.runId, body)
        summary.write(row, 1, run.status, body)
        summary.write_datetime(row, 2, run.createdAt.replace(tzinfo=None), date)
        if run.completedAt is not None:
            summary.write_datetime(row, 3, run.completedAt.replace(tzinfo=None), date)
        summary.write(row, 4, request_text, body)
        summary.write(row, 5, str(run.metadata.get("generatorModel") or ""), body)
        summary.write(row, 6, str(run.metadata.get("reviewerModel") or ""), body)
        summary.write_number(row, 7, run.eventCount, body)
        summary.write(row, 8, run.error or "", body)
        eligibility = _nested_mapping(run.finalResult, "eligibility")
        apparatus = _nested_mapping(run.finalResult, "candidate", "config", "apparatus")
        active_blockers = eligibility.get("activeBlockingAnnotationIds")
        blocker_count = len(active_blockers) if isinstance(active_blockers, list) else 0
        summary.write(row, 9, str(eligibility.get("simulationDisposition") or ""), body)
        summary.write(row, 10, str(eligibility.get("realWorldOperationQualification") or ""), body)
        summary.write_number(row, 11, blocker_count, body)
        summary.write(row, 12, str(apparatus.get("basis") or ""), body)
        summary.write(row, 13, str(eligibility.get("ruleVersion") or ""), body)
        candidate_config = _nested_mapping(run.finalResult, "candidate", "config")
        diagnostics = _nested_mapping(run.finalResult, "diagnostics")
        context_materials = candidate_config.get("contextMaterials")
        diagnostic_issues = diagnostics.get("issues")
        summary.write(
            row,
            14,
            str(
                run.metadata.get("reactionConfigSchemaVersion")
                or candidate_config.get("schemaVersion")
                or ""
            ),
            body,
        )
        summary.write(row, 15, str(run.metadata.get("constraintPolicyVersion") or ""), body)
        summary.write(row, 16, str(run.metadata.get("candidatePreflightRuleVersion") or ""), body)
        search_limit = run.metadata.get("searchMaxResults")
        summary.write(row, 17, "未设置" if search_limit is None else str(search_limit), body)
        summary.write_number(
            row,
            18,
            len(context_materials) if isinstance(context_materials, list) else 0,
            body,
        )
        summary.write_number(
            row,
            19,
            len(diagnostic_issues) if isinstance(diagnostic_issues, list) else 0,
            body,
        )

    model_sheet = _sheet(workbook, "模型轮次", [18, 10, 22, 21, 70], title)
    _headers(model_sheet, ["运行编号", "序号", "事件类型", "时间", "完整事件内容"], title)
    model_row = 1
    model_event_types = {
        "generator_request", "generator_raw_result", "generator_output",
        "reviewer_request", "reviewer_raw_result", "reviewer_output",
        "revision_started", "generation_started", "review_started",
        "candidate_before_apparatus_normalization",
        "apparatus_profile_derived", "eligibility_assessed",
        "consistency_gate_result",
        "review_skipped_after_revision",
        "execution_mode_selected",
        "research_gate_request", "research_gate_raw_result",
        "research_gate_decision", "research_gate_overridden",
        "research_gate_failed", "review_skipped",
        "orchestration_completed",
        "candidate_preflight_completed",
        "workspace_created", "workspace_artifact_written",
        "agent_model_request", "agent_model_response", "agent_model_error",
        "agent_model_retry_scheduled", "agent_model_retry_succeeded",
        "agent_model_retry_exhausted", "agent_model_retry_progress_failed",
        "agent_budget_exhausted", "scientific_report_assembled",
        "scientific_completion_check", "scientific_recovery_started",
        "scientific_recovery_completed", "scientific_recovery_failed",
    }
    for run in run_list:
        for event in run.events:
            if event.eventType not in model_event_types:
                continue
            model_sheet.write(model_row, 0, run.runId, body)
            model_sheet.write_number(model_row, 1, event.sequence, body)
            model_sheet.write(model_row, 2, event.eventType, body)
            model_sheet.write_datetime(model_row, 3, event.createdAt.replace(tzinfo=None), date)
            model_sheet.write(model_row, 4, _json(event.payload), body)
            model_row += 1

    search_sheet = _sheet(
        workbook,
        "检索记录",
        [18, 10, 22, 20, 42, 24, 14, 18, 70],
        title,
    )
    _headers(
        search_sheet,
        [
            "运行编号",
            "序号",
            "事件类型",
            "引擎",
            "检索词",
            "错误类别",
            "HTTP 状态",
            "供应商状态",
            "完整内容",
        ],
        title,
    )
    search_row = 1
    for run in run_list:
        for event in run.events:
            if not event.eventType.startswith("search_"):
                continue
            search_sheet.write(search_row, 0, run.runId, body)
            search_sheet.write_number(search_row, 1, event.sequence, body)
            search_sheet.write(search_row, 2, event.eventType, body)
            search_sheet.write(search_row, 3, str(event.payload.get("engine") or ""), body)
            search_sheet.write(search_row, 4, str(event.payload.get("query") or ""), body)
            search_sheet.write(search_row, 5, str(event.payload.get("category") or ""), body)
            http_status = event.payload.get("httpStatus")
            if isinstance(http_status, int):
                search_sheet.write_number(search_row, 6, http_status, body)
            else:
                search_sheet.write(search_row, 6, str(http_status or ""), body)
            search_sheet.write(
                search_row,
                7,
                str(event.payload.get("providerStatus") or ""),
                body,
            )
            search_sheet.write(search_row, 8, _json(event.payload), body)
            search_row += 1

    issue_sheet = _sheet(workbook, "审核问题", [18, 10, 16, 18, 26, 70], title)
    _headers(issue_sheet, ["运行编号", "序号", "结论", "严重程度", "字段路径", "问题内容"], title)
    issue_row = 1
    for run in run_list:
        for event in run.events:
            if event.eventType != "reviewer_output":
                continue
            report = event.payload.get("report") or event.payload.get("review")
            if not isinstance(report, Mapping):
                continue
            issues = report.get("issues")
            if not isinstance(issues, list) or not issues:
                issues = [{}]
            for issue in issues:
                safe_issue = issue if isinstance(issue, Mapping) else {"message": issue}
                issue_sheet.write(issue_row, 0, run.runId, body)
                issue_sheet.write_number(issue_row, 1, event.sequence, body)
                issue_sheet.write(issue_row, 2, str(report.get("verdict") or ""), body)
                issue_sheet.write(issue_row, 3, str(safe_issue.get("severity") or ""), body)
                issue_sheet.write(
                    issue_row,
                    4,
                    str(safe_issue.get("fieldPath") or safe_issue.get("path") or ""),
                    body,
                )
                issue_sheet.write(
                    issue_row,
                    5,
                    str(safe_issue.get("reason") or safe_issue.get("message") or "无审核问题"),
                    body,
                )
                issue_row += 1

    eligibility_sheet = _sheet(
        workbook,
        "资格判定",
        [18, 10, 30, 24, 22, 14, 18, 80],
        title,
    )
    _headers(
        eligibility_sheet,
        [
            "运行编号",
            "序号",
            "事件类型",
            "模拟资格",
            "真实设备资格",
            "默认阻断数",
            "设备规则版本",
            "完整内容",
        ],
        title,
    )
    eligibility_row = 1
    for run in run_list:
        for event in run.events:
            if event.eventType not in {
                "apparatus_profile_derived",
                "eligibility_assessed",
                "consistency_gate_result",
            }:
                continue
            eligibility = _nested_mapping(event.payload, "eligibility")
            active_blockers = eligibility.get("activeBlockingAnnotationIds")
            blocker_count = (
                len(active_blockers) if isinstance(active_blockers, list) else 0
            )
            eligibility_sheet.write(eligibility_row, 0, run.runId, body)
            eligibility_sheet.write_number(eligibility_row, 1, event.sequence, body)
            eligibility_sheet.write(eligibility_row, 2, event.eventType, body)
            eligibility_sheet.write(
                eligibility_row,
                3,
                str(eligibility.get("simulationDisposition") or ""),
                body,
            )
            eligibility_sheet.write(
                eligibility_row,
                4,
                str(eligibility.get("realWorldOperationQualification") or ""),
                body,
            )
            eligibility_sheet.write_number(eligibility_row, 5, blocker_count, body)
            eligibility_sheet.write(
                eligibility_row,
                6,
                str(
                    eligibility.get("ruleVersion")
                    or event.payload.get("ruleVersion")
                    or ""
                ),
                body,
            )
            eligibility_sheet.write(eligibility_row, 7, _json(event.payload), body)
            eligibility_row += 1

    preflight_sheet = _sheet(
        workbook,
        "配置校验",
        [18, 10, 18, 16, 16, 18, 12, 80],
        title,
    )
    _headers(
        preflight_sheet,
        [
            "运行编号",
            "序号",
            "规则版本",
            "单反应范围",
            "来源衡算",
            "热模型状态",
            "问题数",
            "完整内容",
        ],
        title,
    )
    preflight_row = 1
    for run in run_list:
        for event in run.events:
            if event.eventType != "candidate_preflight_completed":
                continue
            report = _nested_mapping(event.payload, "report")
            issues = report.get("issues")
            issue_count = len(issues) if isinstance(issues, list) else 0
            preflight_sheet.write(preflight_row, 0, run.runId, body)
            preflight_sheet.write_number(preflight_row, 1, event.sequence, body)
            preflight_sheet.write(
                preflight_row, 2, str(report.get("ruleVersion") or ""), body
            )
            preflight_sheet.write(
                preflight_row,
                3,
                "通过" if report.get("singleReactionScopePassed") else "未通过",
                body,
            )
            preflight_sheet.write(
                preflight_row,
                4,
                "通过" if report.get("materialBalancePassed") else "未通过",
                body,
            )
            preflight_sheet.write(
                preflight_row,
                5,
                str(report.get("thermalModelStatus") or ""),
                body,
            )
            preflight_sheet.write_number(preflight_row, 6, issue_count, body)
            preflight_sheet.write(preflight_row, 7, _json(event.payload), body)
            preflight_row += 1

    scientific_sheet = _sheet(
        workbook,
        "科学工具",
        [18, 10, 26, 28, 18, 12, 12, 48, 60, 90],
        title,
    )
    _headers(
        scientific_sheet,
        [
            "运行编号", "序号", "工具调用编号", "工具名称", "状态",
            "耗时毫秒", "随机种子", "工作区文件", "警告", "完整回执",
        ],
        title,
    )
    scientific_row = 1
    for run in run_list:
        for event in run.events:
            if event.eventType not in {
                "scientific_tool_completed", "scientific_tool_inconclusive",
                "scientific_tool_failed",
            }:
                continue
            receipt = _nested_mapping(event.payload, "receipt")
            scientific_sheet.write(scientific_row, 0, run.runId, body)
            scientific_sheet.write_number(scientific_row, 1, event.sequence, body)
            scientific_sheet.write(scientific_row, 2, str(receipt.get("toolCallId") or ""), body)
            scientific_sheet.write(scientific_row, 3, str(receipt.get("toolName") or ""), body)
            scientific_sheet.write(scientific_row, 4, str(receipt.get("status") or ""), body)
            duration = receipt.get("durationMs")
            if isinstance(duration, int):
                scientific_sheet.write_number(scientific_row, 5, duration, body)
            seed = receipt.get("randomSeed")
            if isinstance(seed, int):
                scientific_sheet.write_number(scientific_row, 6, seed, body)
            scientific_sheet.write(scientific_row, 7, str(receipt.get("artifactPath") or ""), body)
            scientific_sheet.write(scientific_row, 8, _json(receipt.get("warnings") or []), body)
            scientific_sheet.write(scientific_row, 9, _json(receipt), body)
            scientific_row += 1

    candidate_sheet = _sheet(
        workbook,
        "候选模型",
        [18, 10, 26, 14, 20, 18, 18, 70],
        title,
    )
    _headers(
        candidate_sheet,
        [
            "运行编号", "事件序号", "模型编号", "是否选中", "状态",
            "可辨识性", "AICc", "完整模型结果",
        ],
        title,
    )
    candidate_row = 1
    for run in run_list:
        for event in run.events:
            receipt = _nested_mapping(event.payload, "receipt")
            result = _nested_mapping(receipt, "result")
            models = result.get("models")
            if not isinstance(models, list):
                continue
            selected_model = result.get("selectedModelId")
            for model in models:
                if not isinstance(model, Mapping):
                    continue
                candidate_sheet.write(candidate_row, 0, run.runId, body)
                candidate_sheet.write_number(candidate_row, 1, event.sequence, body)
                candidate_sheet.write(candidate_row, 2, str(model.get("modelId") or ""), body)
                candidate_sheet.write(candidate_row, 3, "是" if model.get("modelId") == selected_model else "否", body)
                candidate_sheet.write(candidate_row, 4, str(model.get("status") or receipt.get("status") or ""), body)
                candidate_sheet.write(candidate_row, 5, str(model.get("identifiability") or ""), body)
                aicc = model.get("aicc")
                if isinstance(aicc, (int, float)):
                    candidate_sheet.write_number(candidate_row, 6, aicc, body)
                candidate_sheet.write(candidate_row, 7, _json(model), body)
                candidate_row += 1

    parameter_sheet = _sheet(
        workbook,
        "参数来源",
        [18, 24, 44, 16, 18, 28, 28, 60],
        title,
    )
    _headers(
        parameter_sheet,
        [
            "运行编号", "参数编号", "字段路径", "来源类型", "是否支持",
            "来源编号", "工具调用编号", "不确定性",
        ],
        title,
    )
    parameter_row = 1
    for run in run_list:
        report = _nested_mapping(run.finalResult, "scientificAnalysis")
        parameters = report.get("parameterSources")
        if not isinstance(parameters, list):
            rationale = _nested_mapping(
                run.finalResult, "candidate", "scientificRationale"
            )
            parameters = rationale.get("parameterSources")
        if not isinstance(parameters, list):
            continue
        for parameter in parameters:
            if not isinstance(parameter, Mapping):
                continue
            parameter_sheet.write(parameter_row, 0, run.runId, body)
            parameter_sheet.write(parameter_row, 1, str(parameter.get("parameterId") or ""), body)
            parameter_sheet.write(parameter_row, 2, str(parameter.get("fieldPath") or ""), body)
            parameter_sheet.write(parameter_row, 3, str(parameter.get("basis") or ""), body)
            supported = parameter.get("supported")
            parameter_sheet.write(parameter_row, 4, "" if supported is None else ("是" if supported else "否"), body)
            parameter_sheet.write(parameter_row, 5, _json(parameter.get("sourceIds") or []), body)
            parameter_sheet.write(parameter_row, 6, _json(parameter.get("toolCallIds") or []), body)
            parameter_sheet.write(parameter_row, 7, str(parameter.get("uncertainty") or ""), body)
            parameter_row += 1

    route_sheet = _sheet(
        workbook,
        "路线方案",
        [18, 20, 28, 18, 22, 16, 14, 14, 14, 18, 18, 34, 40, 40, 70],
        title,
    )
    _headers(
        route_sheet,
        [
            "运行编号", "方案编号", "方案名称", "方案类型", "模拟就绪状态",
            "是否当前方案", "文献转化率/%", "文献选择性/%", "文献分离收率/%",
            "文献收率", "收率口径", "算术核对", "纯化操作", "杂质风险", "完整方案记录",
        ],
        title,
    )
    route_row = 1
    for run in run_list:
        synthesis = _nested_mapping(
            run.finalResult, "candidate", "researchSynthesis"
        )
        routes = synthesis.get("candidates")
        if not isinstance(routes, list):
            continue
        selected_id = synthesis.get("selectedCandidateId")
        for route in routes:
            if not isinstance(route, Mapping):
                continue
            outcome = _nested_mapping(route, "outcomeAssessment")
            purification = _nested_mapping(route, "purificationAssessment")
            route_sheet.write(route_row, 0, run.runId, body)
            route_sheet.write(route_row, 1, str(route.get("candidateId") or ""), body)
            route_sheet.write(route_row, 2, str(route.get("name") or ""), body)
            route_sheet.write(route_row, 3, str(route.get("scenarioType") or ""), body)
            route_sheet.write(route_row, 4, str(route.get("simulationReadiness") or ""), body)
            route_sheet.write(route_row, 5, "是" if route.get("candidateId") == selected_id else "否", body)
            route_sheet.write(route_row, 6, outcome.get("reportedConversionPercent"), body)
            route_sheet.write(route_row, 7, outcome.get("reportedSelectivityPercent"), body)
            route_sheet.write(route_row, 8, outcome.get("reportedIsolatedYieldPercent"), body)
            route_sheet.write(route_row, 9, str(outcome.get("reportedYield") or route.get("yieldValue") or ""), body)
            route_sheet.write(route_row, 10, str(outcome.get("yieldBasis") or ""), body)
            route_sheet.write(route_row, 11, str(outcome.get("arithmeticConsistency") or ""), body)
            route_sheet.write(route_row, 12, _json(purification.get("operations") or route.get("workup") or []), body)
            route_sheet.write(route_row, 13, _json(purification.get("impurityRisks") or []), body)
            route_sheet.write(route_row, 14, _json(route), body)
            route_row += 1

    raw_sheet = _sheet(workbook, "原始内容分片", [18, 18, 10, 10, 10, 68, 90], title)
    _headers(raw_sheet, ["运行编号", "内容类型", "事件序号", "分片", "总分片", "SHA-256", "原始 JSON"], title)
    raw_row = 1
    for run in run_list:
        complete_json = _json(run.model_dump(mode="json"))
        digest = hashlib.sha256(complete_json.encode("utf-8")).hexdigest()
        chunks = [
            complete_json[index : index + _EXCEL_CELL_CHUNK]
            for index in range(0, len(complete_json), _EXCEL_CELL_CHUNK)
        ] or [""]
        for part, chunk in enumerate(chunks, start=1):
            raw_sheet.write(raw_row, 0, run.runId, body)
            raw_sheet.write(raw_row, 1, "完整运行记录", body)
            raw_sheet.write_blank(raw_row, 2, None, body)
            raw_sheet.write_number(raw_row, 3, part, body)
            raw_sheet.write_number(raw_row, 4, len(chunks), body)
            raw_sheet.write(raw_row, 5, digest, body)
            raw_sheet.write(raw_row, 6, chunk, body)
            raw_row += 1

    workbook.close()
    return output.getvalue()


def _sheet(workbook, name: str, widths: list[int], title):
    sheet = workbook.add_worksheet(name)
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, 0, len(widths) - 1)
    sheet.set_row(0, 24, title)
    for column, width in enumerate(widths):
        sheet.set_column(column, column, width)
    return sheet


def _nested_mapping(value: Any, *keys: str) -> Mapping[str, Any]:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return current if isinstance(current, Mapping) else {}


def _headers(sheet, headers: list[str], title) -> None:
    for column, header in enumerate(headers):
        sheet.write(0, column, header, title)
