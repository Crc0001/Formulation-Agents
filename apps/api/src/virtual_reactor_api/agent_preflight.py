"""Structured deterministic preflight for generated reaction candidates."""

from __future__ import annotations

import math

from virtual_reactor_api.agent_models import (
    CandidatePreflightReport,
    CandidateReactionConfig,
    EligibilityIssue,
)
from virtual_reactor_api.agent_prompts import FRONTEND_CAPABILITIES
from virtual_reactor_api.reaction_depiction import parse_reaction_smiles


SOURCE_BALANCE_TOLERANCE = 1e-9
LITERATURE_ENDPOINT_TOLERANCE_PERCENTAGE_POINTS = 3.0


def validate_candidate_preflight(
    candidate: CandidateReactionConfig,
) -> CandidatePreflightReport:
    config = candidate.config
    issues: list[EligibilityIssue] = []
    scope_passed = True
    balance_passed = True
    species_by_id = {item.id: item for item in config.species}
    control_ids = {item.id for item in config.controls}
    controls_by_id = {item.id: item for item in config.controls}
    evidence_ids = {item.id for item in config.evidence}
    equivalents = config.materialBalance.sourceEquivalentBySpecies

    def add_issue(code: str, path: str, message: str) -> None:
        issues.append(
            EligibilityIssue(
                code=code,
                fieldPath=path,
                scope="simulation",
                severity="block",
                message=message,
            )
        )

    equation = config.reaction.equation
    if equation is not None:
        try:
            parse_reaction_smiles(equation.reactionSmiles)
        except ValueError:
            add_issue(
                "invalid_reaction_smiles",
                "/config/reaction/equation/reactionSmiles",
                "本次模拟反应式无法解析为包含反应物和产物的 Reaction SMILES。",
            )
        for index, evidence_id in enumerate(equation.evidenceIds):
            if evidence_id not in evidence_ids:
                add_issue(
                    "unknown_reaction_equation_evidence",
                    f"/config/reaction/equation/evidenceIds/{index}",
                    f"本次模拟反应式引用了未知依据“{evidence_id}”。",
                )

    primary = species_by_id.get(config.scope.primarySubstrateId)
    target = species_by_id.get(config.scope.targetProductId)
    if primary is None or primary.role != "substrate":
        scope_passed = False
        add_issue(
            "invalid_primary_substrate",
            "/config/scope/primarySubstrateId",
            "主底物标识必须引用一个已声明的 substrate 物种。",
        )
    if target is None or target.role != "product":
        scope_passed = False
        add_issue(
            "invalid_target_product",
            "/config/scope/targetProductId",
            "目标产物标识必须引用一个已声明的 product 物种。",
        )
    if config.materialBalance.basisSpeciesId != config.scope.primarySubstrateId:
        balance_passed = False
        add_issue(
            "invalid_balance_basis",
            "/config/materialBalance/basisSpeciesId",
            "来源衡算基准物种必须与单反应范围中的主底物一致。",
        )
    for index, evidence_id in enumerate(config.scope.evidenceIds):
        if evidence_id not in evidence_ids:
            scope_passed = False
            add_issue(
                "unknown_scope_evidence",
                f"/config/scope/evidenceIds/{index}",
                f"单反应范围引用了未知依据“{evidence_id}”。",
            )

    for material_index, material in enumerate(config.contextMaterials):
        for evidence_index, evidence_id in enumerate(material.evidenceIds):
            if evidence_id not in evidence_ids:
                add_issue(
                    "unknown_context_material_evidence",
                    (
                        f"/config/contextMaterials/{material_index}"
                        f"/evidenceIds/{evidence_index}"
                    ),
                    f"上下文物料“{material.id}”引用了未知依据“{evidence_id}”。",
                )

    for species_id, equivalent in equivalents.items():
        if species_id not in species_by_id:
            balance_passed = False
            add_issue(
                "unknown_balance_species",
                f"/config/materialBalance/sourceEquivalentBySpecies/{species_id}",
                f"来源当量映射引用了未知物种“{species_id}”。",
            )
        if not math.isfinite(equivalent) or equivalent <= 0:
            balance_passed = False
            add_issue(
                "invalid_source_equivalent",
                f"/config/materialBalance/sourceEquivalentBySpecies/{species_id}",
                f"物种“{species_id}”的主底物来源当量必须为正有限数。",
            )
    for species_id, label in (
        (config.scope.primarySubstrateId, "主底物"),
        (config.scope.targetProductId, "目标产物"),
    ):
        if species_id not in equivalents:
            balance_passed = False
            add_issue(
                "missing_source_equivalent",
                "/config/materialBalance/sourceEquivalentBySpecies",
                f"{label}“{species_id}”必须声明主底物来源当量。",
            )

    for index, reaction in enumerate(config.reactions):
        for evidence_index, evidence_id in enumerate(reaction.evidenceIds):
            if evidence_id not in evidence_ids:
                add_issue(
                    "unknown_reaction_evidence",
                    f"/config/reactions/{index}/evidenceIds/{evidence_index}",
                    f"反应“{reaction.id}”引用了未知依据“{evidence_id}”。",
                )
        tracked = set(reaction.stoichiometry) & set(equivalents)
        if not tracked:
            balance_passed = False
            add_issue(
                "reaction_outside_source_balance",
                f"/config/reactions/{index}/stoichiometry",
                f"反应“{reaction.id}”没有涉及任何主底物来源物种，不属于所选单一反应阶段。",
            )
            continue
        residual = sum(
            coefficient * equivalents.get(species_id, 0.0)
            for species_id, coefficient in reaction.stoichiometry.items()
        )
        if not math.isfinite(residual) or abs(residual) > SOURCE_BALANCE_TOLERANCE:
            balance_passed = False
            add_issue(
                "source_balance_nonconservation",
                f"/config/reactions/{index}/stoichiometry",
                f"反应“{reaction.id}”不满足主底物来源当量守恒。",
            )

    if primary is not None and target is not None and not _main_path_reaches_target(
        candidate, primary.id, target.id
    ):
        scope_passed = False
        add_issue(
            "target_not_reachable",
            "/config/scope/targetProductId",
            "目标产物无法沿声明的主反应路径从主底物到达。",
        )

    amount_units = {
        *(item.initialAmount.unit for item in config.species),
        *(item.totalAmount.unit for item in config.operations),
        *(item.normalizationAmount.unit for item in config.reactions),
    }
    if len(amount_units) != 1:
        add_issue(
            "amount_unit_mismatch",
            "/config",
            "全部物种初始量、加料总量和反应归一化量必须使用同一个 amount 单位。",
        )

    used_controls: set[str] = set()
    for index, species in enumerate(config.species):
        control_id = species.initialAmountControlId
        if control_id is None:
            continue
        used_controls.add(control_id)
        control = controls_by_id.get(control_id)
        if control is None:
            add_issue(
                "unknown_initial_amount_control",
                f"/config/species/{index}/initialAmountControlId",
                f"物种“{species.id}”引用了未知初始投料控制项“{control_id}”。",
            )
        elif control.unit != species.initialAmount.unit:
            add_issue(
                "initial_amount_control_unit_mismatch",
                f"/config/species/{index}/initialAmountControlId",
                f"物种“{species.id}”的初始投料控制项必须使用 {species.initialAmount.unit}。",
            )

    end_control_id = config.simulation.endMinuteControlId
    if end_control_id is not None:
        used_controls.add(end_control_id)
        end_control = controls_by_id.get(end_control_id)
        if end_control is None:
            add_issue(
                "unknown_end_time_control",
                "/config/simulation/endMinuteControlId",
                f"模拟引用了未知反应时长控制项“{end_control_id}”。",
            )
        elif end_control.unit != "min":
            add_issue(
                "end_time_control_unit_mismatch",
                "/config/simulation/endMinuteControlId",
                "反应时长控制项必须使用 min。",
            )

    integration_intervals = config.simulation.endMinute / config.simulation.stepMinute
    if integration_intervals < 120:
        add_issue(
            "insufficient_time_resolution",
            "/config/simulation/stepMinute",
            "积分时间点过少；单次模拟至少需要 120 个积分区间，以免趋势曲线失真。",
        )

    for index, control in enumerate(config.controls):
        if control.default.unit != control.unit:
            add_issue(
                "control_unit_mismatch",
                f"/config/controls/{index}/default/unit",
                f"控制项“{control.id}”默认值单位必须与声明单位一致。",
            )
        if not (
            control.bands.hard.minimum
            <= control.default.value
            <= control.bands.hard.maximum
        ):
            add_issue(
                "control_default_outside_hard_range",
                f"/config/controls/{index}/default/value",
                f"控制项“{control.id}”默认值必须位于硬范围内。",
            )

    for index, operation in enumerate(config.operations):
        if operation.speciesId not in species_by_id:
            add_issue(
                "unknown_operation_species",
                f"/config/operations/{index}/speciesId",
                f"加料操作“{operation.id}”引用了未知物种“{operation.speciesId}”。",
            )
        for field_name, control_id in (
            ("amountControlId", operation.amountControlId),
            ("rateControlId", operation.rateControlId),
        ):
            if control_id is None:
                continue
            used_controls.add(control_id)
            if control_id not in control_ids:
                add_issue(
                    "unknown_operation_control",
                    f"/config/operations/{index}/{field_name}",
                    f"加料操作“{operation.id}”引用了未知控制项“{control_id}”。",
                )

    for reaction_index, reaction in enumerate(config.reactions):
        referenced_species = set(reaction.stoichiometry) | set(reaction.orders)
        for species_id in sorted(referenced_species - set(species_by_id)):
            add_issue(
                "unknown_reaction_species",
                f"/config/reactions/{reaction_index}",
                f"反应“{reaction.id}”引用了未知物种“{species_id}”。",
            )
        if reaction.normalizationAmount.value <= 0:
            add_issue(
                "invalid_normalization_amount",
                f"/config/reactions/{reaction_index}/normalizationAmount/value",
                f"反应“{reaction.id}”的归一化量必须大于零。",
            )
        for modifier_index, modifier in enumerate(reaction.modifiers):
            if modifier.controlId is not None:
                used_controls.add(modifier.controlId)
            if modifier.controlId is not None and modifier.controlId not in control_ids:
                add_issue(
                    "unknown_modifier_control",
                    f"/config/reactions/{reaction_index}/modifiers/{modifier_index}/controlId",
                    f"反应“{reaction.id}”引用了未知控制项“{modifier.controlId}”。",
                )
            if (
                modifier.processVariableId == "reactor_temperature"
                and config.thermalModel is None
            ):
                add_issue(
                    "temperature_modifier_without_thermal_model",
                    f"/config/reactions/{reaction_index}/modifiers/{modifier_index}/processVariableId",
                    f"反应“{reaction.id}”使用了反应器温度速率修饰，但配置没有热模型；请配置完整热模型，或改用已声明的温度控制项表达恒温条件。",
                )

    thermal_status = "not_configured"
    if config.thermalModel is not None:
        thermal_status = "valid"
        used_controls.add(config.thermalModel.jacketTemperatureControlId)
        thermal_issue_count = len(issues)
        _validate_thermal_model(
            candidate,
            control_ids,
            evidence_ids,
            add_issue,
        )
        if len(issues) > thermal_issue_count:
            thermal_status = "invalid"

    for index, control in enumerate(config.controls):
        if control.id not in used_controls:
            add_issue(
                "unused_control",
                f"/config/controls/{index}",
                f"控制项“{control.id}”没有连接任何加料、反应速率或已注册模型原语。",
            )

    mixing_control_terms = (
        "搅拌",
        "转速",
        "混合强度",
        "混合程度",
        "stir",
        "mixing_rate",
        "mixing_intensity",
        "agit",
        "rpm",
    )
    has_mixing_control = any(
        any(
            term in f"{control.id} {control.label}".lower()
            for term in mixing_control_terms
        )
        and control.id in used_controls
        for control in config.controls
    )
    has_mixing_exclusion = any(
        any(term in limitation.lower() for term in ("搅拌", "混合", "stir", "mixing", "agit"))
        and any(
            reason in limitation.lower()
            for reason in ("缺少", "无依据", "未建模", "不适用", "unknown", "not modeled")
        )
        for limitation in config.apparatus.limitations
    )
    if config.apparatus.kind in {"batch", "semi_batch"} and not (
        has_mixing_control or has_mixing_exclusion
    ):
        add_issue(
            "missing_mixing_treatment",
            "/config/apparatus/limitations",
            "液相釜式或半间歇配置必须提供已连接的搅拌/混合控制；若缺少定量依据或确实不适用，必须在设备局限中明确说明原因，不能静默省略。",
        )

    for index, observable in enumerate(config.observables):
        if observable.speciesId is not None and observable.speciesId not in species_by_id:
            add_issue(
                "unknown_observable_species",
                f"/config/observables/{index}/speciesId",
                f"观测量“{observable.id}”引用了未知物种“{observable.speciesId}”。",
            )

    unsupported_charts = set(config.presentation.chartIds) - set(
        FRONTEND_CAPABILITIES["chartIds"]
    )
    unsupported_animations = set(config.presentation.animationIds) - set(
        FRONTEND_CAPABILITIES["animationIds"]
    )
    if unsupported_charts:
        add_issue(
            "unsupported_chart",
            "/config/presentation/chartIds",
            "配置包含前端不支持的图表能力：" + "、".join(sorted(unsupported_charts)) + "。",
        )
    if unsupported_animations:
        add_issue(
            "unsupported_animation",
            "/config/presentation/animationIds",
            "配置包含前端不支持的动画能力："
            + "、".join(sorted(unsupported_animations))
            + "。",
        )

    _validate_selected_research_scenario(candidate, add_issue)

    _validate_literature_endpoint_alignment(candidate, add_issue)

    for alternative in candidate.alternativeConfigs:
        synthesis = candidate.researchSynthesis
        if synthesis is None:
            continue
        alternative_candidate = candidate.model_copy(
            update={
                "config": alternative.config,
                "alternativeConfigs": [],
                "researchSynthesis": synthesis.model_copy(
                    update={
                        "selectedCandidateId": alternative.candidateId,
                        "selectionStatus": "selected",
                    }
                ),
            }
        )
        alternative_report = validate_candidate_preflight(alternative_candidate)
        for issue in alternative_report.issues:
            add_issue(
                "alternative_" + issue.code,
                f"/candidate/alternativeConfigs/{alternative.candidateId}{issue.fieldPath}",
                f"备选方案“{alternative.candidateId}”：{issue.message}",
            )

    return CandidatePreflightReport(
        executable=not issues,
        singleReactionScopePassed=scope_passed,
        materialBalancePassed=balance_passed,
        thermalModelStatus=(
            thermal_status
        ),
        issues=issues,
    )


def _validate_literature_endpoint_alignment(candidate, add_issue) -> None:
    """Reject a claimed calibration when the executable config misses its source endpoint."""
    synthesis = candidate.researchSynthesis
    if synthesis is None or synthesis.selectedCandidateId is None:
        return
    selected = next(
        (item for item in synthesis.candidates if item.candidateId == synthesis.selectedCandidateId),
        None,
    )
    if selected is None or selected.outcomeAssessment is None:
        return
    expected = selected.outcomeAssessment
    if (
        expected.reportedConversionPercent is None
        and expected.reportedSelectivityPercent is None
    ):
        return
    metrics = _simulate_default_reaction_metrics(candidate)
    if metrics is None:
        add_issue(
            "literature_endpoint_not_checkable",
            "/candidate/researchSynthesis/candidates/"
            + selected.candidateId
            + "/outcomeAssessment",
            "当前配置含有预检尚不能复算的加料或过程模型，不能声称已按文献终点完成校准。",
        )
        return
    for name, actual, target, label in (
        (
            "conversion",
            metrics["conversionPercent"],
            expected.reportedConversionPercent,
            "转化率",
        ),
        (
            "selectivity",
            metrics["selectivityPercent"],
            expected.reportedSelectivityPercent,
            "选择性",
        ),
    ):
        if target is None:
            continue
        difference = abs(actual - target)
        if difference > LITERATURE_ENDPOINT_TOLERANCE_PERCENTAGE_POINTS:
            add_issue(
                f"literature_{name}_mismatch",
                "/candidate/researchSynthesis/candidates/"
                + selected.candidateId
                + f"/outcomeAssessment/reported{label}Percent",
                f"默认条件模拟{label}为 {actual:.2f}%，文献终点为 {target:.2f}%，相差 {difference:.2f} 个百分点；请修正模型参数或撤销已校准声明。",
            )


def _simulate_default_reaction_metrics(candidate) -> dict[str, float] | None:
    config = candidate.config
    if config.operations or config.thermalModel is not None:
        return None
    controls = {item.id: item.default.value for item in config.controls}
    amounts = {
        item.id: (
            controls[item.initialAmountControlId]
            if item.initialAmountControlId is not None
            else item.initialAmount.value
        )
        for item in config.species
    }
    initial = dict(amounts)
    end_minute = (
        controls[config.simulation.endMinuteControlId]
        if config.simulation.endMinuteControlId is not None
        else config.simulation.endMinute
    )
    steps = max(1, math.ceil(end_minute / config.simulation.stepMinute))
    for step_index in range(steps):
        duration = min(
            config.simulation.stepMinute,
            end_minute - step_index * config.simulation.stepMinute,
        )
        if duration <= 0:
            break
        before = dict(amounts)
        extents: list[tuple[object, float]] = []
        for reaction in config.reactions:
            normalization = reaction.normalizationAmount.value
            extent = normalization * reaction.rateConstantPerMinute * duration
            for species_id, order in reaction.orders.items():
                extent *= (before[species_id] / normalization) ** order
            for modifier in reaction.modifiers:
                if modifier.controlId is None:
                    return None
                value = controls[modifier.controlId]
                raw = 1 + modifier.coefficient * (value - modifier.reference)
                extent *= min(modifier.maximumFactor, max(modifier.minimumFactor, raw))
            extents.append((reaction, max(0.0, extent)))
        factors = [1.0] * len(extents)
        for species_id, available in before.items():
            demand = sum(
                extent * -reaction.stoichiometry.get(species_id, 0)
                for reaction, extent in extents
                if reaction.stoichiometry.get(species_id, 0) < 0
            )
            if demand > available and demand > 0:
                factor = available / demand
                for index, (reaction, _) in enumerate(extents):
                    if reaction.stoichiometry.get(species_id, 0) < 0:
                        factors[index] = min(factors[index], factor)
        for (reaction, extent), factor in zip(extents, factors, strict=True):
            bounded = extent * factor
            for species_id, coefficient in reaction.stoichiometry.items():
                amounts[species_id] = max(0.0, amounts[species_id] + coefficient * bounded)
    substrate_id = config.scope.primarySubstrateId
    product_id = config.scope.targetProductId
    substrate_initial = initial[substrate_id]
    consumed = max(0.0, substrate_initial - amounts[substrate_id])
    product_equivalent = config.materialBalance.sourceEquivalentBySpecies[product_id]
    product_from_basis = amounts[product_id] * product_equivalent
    return {
        "conversionPercent": 100 * consumed / substrate_initial,
        "selectivityPercent": 0.0 if consumed == 0 else 100 * product_from_basis / consumed,
        "reactionYieldPercent": 100 * product_from_basis / substrate_initial,
    }


def _validate_selected_research_scenario(candidate, add_issue) -> None:
    synthesis = candidate.researchSynthesis
    if synthesis is None or synthesis.selectedCandidateId is None:
        return
    selected = next(
        (
            item
            for item in synthesis.candidates
            if item.candidateId == synthesis.selectedCandidateId
        ),
        None,
    )
    if selected is None:
        return
    base_path = "/candidate/researchSynthesis/candidates/" + selected.candidateId
    if selected.outcomeAssessment is None:
        add_issue(
            "missing_route_outcome_assessment",
            base_path + "/outcomeAssessment",
            "当前方案尚未区分文献收率口径并核对数据一致性，不能载入模拟。",
        )
    if selected.purificationAssessment is None:
        add_issue(
            "missing_route_purification_assessment",
            base_path + "/purificationAssessment",
            "当前方案尚未评估纯化步骤、分离依据和杂质风险，不能载入模拟。",
        )
    sources = {
        item.sourceId: item
        for item in synthesis.sources
        if item.sourceId in selected.sourceIds
    }
    direct_access = any(
        source.sourceType
        in {"primary_paper", "patent_example", "user_process_record"}
        and source.accessLevel in {"full_text", "example_text", "user_provided"}
        for source in sources.values()
    )
    if not direct_access:
        add_issue(
            "selected_route_lacks_direct_conditions",
            base_path + "/sourceIds",
            "当前方案只有摘要、检索片段或类比证据，尚不足以作为可执行模拟条件。",
        )
    if selected.simulationReadiness != "configured":
        add_issue(
            "selected_route_not_configured",
            base_path + "/simulationReadiness",
            "当前方案未声明为经过独立配置的模拟方案。",
        )
    source_by_id = {item.sourceId: item for item in synthesis.sources}
    unread_patent_candidates = [
        item.candidateId
        for item in synthesis.candidates
        if item.candidateId != selected.candidateId
        and any(
            source_by_id.get(source_id) is not None
            and source_by_id[source_id].sourceType == "patent_document"
            and source_by_id[source_id].accessLevel in {"abstract", "snippet"}
            for source_id in item.sourceIds
        )
    ]
    if unread_patent_candidates:
        add_issue(
            "unread_patent_route_candidates",
            "/candidate/researchSynthesis/candidates",
            "仍有已识别的相关专利候选未读取实施例全文，不能提前宣布跨路线优选："
            + "、".join(unread_patent_candidates)
            + "。",
        )


def _main_path_reaches_target(
    candidate: CandidateReactionConfig,
    start_species_id: str,
    target_species_id: str,
) -> bool:
    reachable = {start_species_id}
    changed = True
    while changed:
        changed = False
        for reaction in candidate.config.reactions:
            if reaction.pathway != "main":
                continue
            if not any(
                coefficient < 0 and species_id in reachable
                for species_id, coefficient in reaction.stoichiometry.items()
            ):
                continue
            for species_id, coefficient in reaction.stoichiometry.items():
                if coefficient > 0 and species_id not in reachable:
                    reachable.add(species_id)
                    changed = True
    return target_species_id in reachable


def _validate_thermal_model(
    candidate: CandidateReactionConfig,
    control_ids: set[str],
    evidence_ids: set[str],
    add_issue,
) -> None:
    config = candidate.config
    model = config.thermalModel
    if model is None:
        return
    amount_unit = config.species[0].initialAmount.unit
    expected_units = {
        "/config/thermalModel/initialReactorTemperature": (
            model.initialReactorTemperature,
            "degC",
        ),
        "/config/thermalModel/effectiveHeatCapacity": (
            model.effectiveHeatCapacity,
            "kJ/K",
        ),
        "/config/thermalModel/jacketConductance": (
            model.jacketConductance,
            "kJ/(min*K)",
        ),
        "/config/thermalModel/maximumCoolingRate": (
            model.maximumCoolingRate,
            "kJ/min",
        ),
    }
    if model.ambientTemperature is not None:
        expected_units["/config/thermalModel/ambientTemperature"] = (
            model.ambientTemperature,
            "degC",
        )
    if model.ambientConductance is not None:
        expected_units["/config/thermalModel/ambientConductance"] = (
            model.ambientConductance,
            "kJ/(min*K)",
        )
    for path, (parameter, expected_unit) in expected_units.items():
        _validate_thermal_parameter(
            parameter, path, expected_unit, evidence_ids, add_issue
        )
    if model.jacketTemperatureControlId not in control_ids:
        add_issue(
            "unknown_thermal_control",
            "/config/thermalModel/jacketTemperatureControlId",
            "热模型引用了未知夹套温度控制项。",
        )

    reaction_ids = {reaction.id for reaction in config.reactions}
    enthalpy_ids = {entry.reactionId for entry in model.reactionEnthalpies}
    if reaction_ids != enthalpy_ids:
        add_issue(
            "incomplete_reaction_enthalpies",
            "/config/thermalModel/reactionEnthalpies",
            "启用热模型时必须且只能为每条反应声明一个反应焓。",
        )
    for index, entry in enumerate(model.reactionEnthalpies):
        _validate_thermal_parameter(
            entry.enthalpyChangePerAmount,
            f"/config/thermalModel/reactionEnthalpies/{index}/enthalpyChangePerAmount",
            f"kJ/{amount_unit}",
            evidence_ids,
            add_issue,
        )

    feed_terms = model.feedThermalTerms
    operation_ids = {operation.id for operation in config.operations}
    feed_ids = {entry.operationId for entry in feed_terms}
    if operation_ids != feed_ids:
        add_issue(
            "incomplete_feed_thermal_terms",
            "/config/thermalModel/feedThermalTerms",
            "启用热模型时必须且只能为每个加料操作声明入口温度和单位物质的量热容。",
        )
    for index, entry in enumerate(feed_terms):
        _validate_thermal_parameter(
            entry.inletTemperature,
            f"/config/thermalModel/feedThermalTerms/{index}/inletTemperature",
            "degC",
            evidence_ids,
            add_issue,
        )
        _validate_thermal_parameter(
            entry.heatCapacityPerAmount,
            f"/config/thermalModel/feedThermalTerms/{index}/heatCapacityPerAmount",
            f"kJ/({amount_unit}*K)",
            evidence_ids,
            add_issue,
        )


def _validate_thermal_parameter(
    parameter,
    path: str,
    expected_unit: str,
    evidence_ids: set[str],
    add_issue,
) -> None:
    if parameter.quantity.unit != expected_unit:
        add_issue(
            "thermal_unit_mismatch",
            f"{path}/quantity/unit",
            f"热参数必须使用单位“{expected_unit}”。",
        )
    for index, evidence_id in enumerate(parameter.evidenceIds):
        if evidence_id not in evidence_ids:
            add_issue(
                "unknown_thermal_evidence",
                f"{path}/evidenceIds/{index}",
                f"热参数引用了未知依据“{evidence_id}”。",
            )
