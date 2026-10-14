"""LangChain-compatible wrappers for constrained scientific functions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from threading import Lock
from time import perf_counter
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import ValidationError

from virtual_reactor_api.scientific.contracts import (
    ChemicalIdentityInput,
    IdentifiabilityInput,
    KineticSimulationInput,
    ModelComparisonInput,
    QuantityValidationInput,
    ScientificToolStatus,
    StoichiometryAnalysisInput,
)
from virtual_reactor_api.scientific.identifiability import (
    assess_parameter_identifiability,
)
from virtual_reactor_api.scientific.identity import inspect_chemical_identity
from virtual_reactor_api.scientific.kinetics import (
    fit_and_compare_models,
    simulate_candidate_kinetics,
)
from virtual_reactor_api.scientific.ledger import ScientificRunLedger
from virtual_reactor_api.scientific.stoichiometry import analyze_stoichiometry
from virtual_reactor_api.scientific.units import validate_quantities_and_units


@dataclass(frozen=True, slots=True)
class ScientificToolLimits:
    callBudgets: dict[str, int] = field(default_factory=dict)
    defaultCallBudget: int | None = None
    maximumDurationSeconds: float = 30.0
    maximumSerializedBytes: int = 1_000_000

    def budget_for(self, tool_name: str) -> int | None:
        return self.callBudgets.get(tool_name, self.defaultCallBudget)


class ScientificToolRuntime:
    def __init__(
        self,
        *,
        ledger: ScientificRunLedger,
        limits: ScientificToolLimits | None = None,
    ) -> None:
        self.ledger = ledger
        self.limits = limits or ScientificToolLimits()
        self._counts: dict[str, int] = {}
        self._lock = Lock()

    def consume(self, tool_name: str) -> bool:
        with self._lock:
            count = self._counts.get(tool_name, 0)
            self._counts[tool_name] = count + 1
            budget = self.limits.budget_for(tool_name)
            return budget is None or count < budget


@dataclass(frozen=True, slots=True)
class _ToolDefinition:
    name: str
    description: str
    input_model: type
    function: Callable[[Any], Any]
    applicability: tuple[str, ...]


_DEFINITIONS = (
    _ToolDefinition(
        "inspect_chemical_identity",
        "用 RDKit 校验明确提供的 SMILES、分子式和摩尔质量；不会从名称猜结构。",
        ChemicalIdentityInput,
        inspect_chemical_identity,
        ("仅校验请求中明确提供的结构信息",),
    ),
    _ToolDefinition(
        "validate_quantities_and_units",
        "用 Pint 校验量纲并执行显式单位转换，包括绝对温度和温差。",
        QuantityValidationInput,
        validate_quantities_and_units,
        ("只认可工具契约声明的量纲类别",),
    ),
    _ToolDefinition(
        "analyze_stoichiometry",
        "检查元素守恒、化学计量矩阵秩、限制试剂和理论最大反应进度。",
        StoichiometryAnalysisInput,
        analyze_stoichiometry,
        ("不会自动配平或修改提交的反应式",),
    ),
    _ToolDefinition(
        "assess_parameter_identifiability",
        "根据观测数量和灵敏度矩阵判断参数能否唯一识别。",
        IdentifiabilityInput,
        assess_parameter_identifiability,
        ("结论仅适用于提交的候选模型、观测和灵敏度矩阵",),
    ),
    _ToolDefinition(
        "simulate_candidate_kinetics",
        "使用 SciPy 积分受限声明式质量作用动力学模型。",
        KineticSimulationInput,
        simulate_candidate_kinetics,
        ("数值结果仅适用于声明的模型、参数范围和时间网格",),
    ),
    _ToolDefinition(
        "fit_and_compare_models",
        "用有界最小二乘拟合候选模型并比较可辨识性与 AIC/AICc。",
        ModelComparisonInput,
        fit_and_compare_models,
        ("只有数据充分且参数可辨识时才把结果标记为拟合",),
    ),
)


def create_scientific_tools(runtime: ScientificToolRuntime) -> list[BaseTool]:
    return [_create_tool(definition, runtime) for definition in _DEFINITIONS]


def _create_tool(
    definition: _ToolDefinition,
    runtime: ScientificToolRuntime,
) -> StructuredTool:
    def invoke(**kwargs: Any) -> str:
        normalized = _json_value(kwargs)
        call = runtime.ledger.start(definition.name, normalized)
        if not runtime.consume(definition.name):
            return _receipt_json(
                runtime.ledger.fail(
                    call,
                    f"工具 {definition.name} 已达到本次运行调用预算。",
                    status="insufficient_data",
                )
            )
        started = perf_counter()
        try:
            request = definition.input_model.model_validate(kwargs)
            result = definition.function(request)
        except (ValidationError, ValueError, TypeError) as error:
            return _receipt_json(
                runtime.ledger.fail(
                    call,
                    f"科学工具输入无效：{str(error)}",
                    status="invalid_input",
                )
            )
        elapsed = perf_counter() - started
        if elapsed > runtime.limits.maximumDurationSeconds:
            return _receipt_json(
                runtime.ledger.fail(
                    call,
                    "科学工具执行超过本次运行时间限制。",
                    status="numerical_failure",
                )
            )
        result_payload = result.model_dump(mode="json")
        encoded = json.dumps(
            result_payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        if len(encoded) > runtime.limits.maximumSerializedBytes:
            return _receipt_json(
                runtime.ledger.fail(
                    call,
                    "科学工具输出超过本次运行大小限制。",
                    status="numerical_failure",
                )
            )
        status: ScientificToolStatus = result.status
        receipt = runtime.ledger.complete(
            call,
            status=status,
            result=result_payload,
            warnings=_warnings(result_payload, status),
            assumptions=[],
            applicability=list(definition.applicability),
        )
        return _receipt_json(receipt)

    return StructuredTool.from_function(
        func=invoke,
        name=definition.name,
        description=definition.description,
        args_schema=definition.input_model,
    )


def _warnings(payload: dict[str, Any], status: ScientificToolStatus) -> list[str]:
    warnings: list[str] = []
    direct = payload.get("warnings")
    if isinstance(direct, list):
        warnings.extend(str(item) for item in direct if str(item).strip())
    for collection_name in ("species", "quantities", "models"):
        collection = payload.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            nested = item.get("warnings")
            if isinstance(nested, list):
                warnings.extend(str(value) for value in nested if str(value).strip())
            error = item.get("error")
            if isinstance(error, str) and error.strip():
                warnings.append(error)
            if status != "success" and isinstance(item.get("message"), str):
                warnings.append(item["message"])
    if status != "success" and not warnings:
        message = payload.get("message")
        warnings.append(str(message) if message else "科学工具未产生成功结果。")
    return list(dict.fromkeys(warnings))


def _receipt_json(receipt: Any) -> str:
    return json.dumps(
        receipt.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)
