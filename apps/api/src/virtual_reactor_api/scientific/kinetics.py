"""Bounded ODE simulation and deterministic kinetic model comparison."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from pydantic import Field
from scipy.integrate import solve_ivp
from scipy.linalg import null_space
from scipy.optimize import least_squares

from virtual_reactor_api.contracts import StrictModel
from virtual_reactor_api.scientific.contracts import (
    CandidateKineticModel,
    FiniteNumber,
    IdentifiabilityVerdict,
    KineticSimulationInput,
    ModelComparisonInput,
    NonBlankText,
    ScientificToolStatus,
)


class KineticSimulationResult(StrictModel):
    status: ScientificToolStatus
    times: list[FiniteNumber]
    series: dict[str, list[FiniteNumber]]
    minimumState: FiniteNumber
    maximumConservationDrift: FiniteNumber
    functionEvaluations: int = Field(ge=0)
    message: NonBlankText


class ModelFitResult(StrictModel):
    modelId: NonBlankText
    status: ScientificToolStatus
    parameters: dict[str, FiniteNumber]
    residualSumSquares: FiniteNumber | None
    degreesOfFreedom: int
    jacobianRank: int | None
    conditionNumber: FiniteNumber | None
    identifiability: IdentifiabilityVerdict
    aic: FiniteNumber | None
    aicc: FiniteNumber | None
    calibrationTimeRange: tuple[FiniteNumber, FiniteNumber] | None
    parameterBasisChangedToFitted: bool
    message: NonBlankText


class ModelComparisonResult(StrictModel):
    status: ScientificToolStatus
    selectedModelId: str | None
    models: list[ModelFitResult]
    randomSeed: int


class _FunctionBudgetExceeded(RuntimeError):
    pass


def simulate_candidate_kinetics(
    request: KineticSimulationInput,
) -> KineticSimulationResult:
    compiled = _compile_model(request.model)
    initial = np.array(
        [request.initialAmounts[species_id] for species_id in compiled.species_ids],
        dtype=float,
    )
    evaluations = 0

    def right_hand_side(_time: float, state: np.ndarray) -> np.ndarray:
        nonlocal evaluations
        evaluations += 1
        if evaluations > request.maximumFunctionEvaluations:
            raise _FunctionBudgetExceeded
        safe_state = np.maximum(state, 0.0)
        rates = np.empty(len(compiled.reactions), dtype=float)
        for reaction_index, reaction in enumerate(compiled.reactions):
            rate = compiled.parameter_values[reaction.rate_parameter_index]
            for species_index, order in reaction.orders:
                rate *= safe_state[species_index] ** order
            rates[reaction_index] = rate
        return compiled.stoichiometric_matrix @ rates

    try:
        solution = solve_ivp(
            right_hand_side,
            (request.times[0], request.times[-1]),
            initial,
            t_eval=np.asarray(request.times, dtype=float),
            rtol=request.relativeTolerance,
            atol=request.absoluteTolerance,
            max_step=request.maximumStep or np.inf,
            method="RK45",
        )
    except _FunctionBudgetExceeded:
        return _simulation_failure(
            request, evaluations, "数值积分超过函数调用预算。"
        )
    except (FloatingPointError, ValueError, OverflowError) as error:
        return _simulation_failure(
            request, evaluations, f"数值积分失败：{str(error) or error.__class__.__name__}"
        )
    if not solution.success:
        return _simulation_failure(request, evaluations, f"数值积分失败：{solution.message}")
    values = np.asarray(solution.y, dtype=float)
    if not np.all(np.isfinite(values)):
        return _simulation_failure(request, evaluations, "数值积分产生非有限状态。")
    minimum = float(np.min(values))
    negative_tolerance = max(request.absoluteTolerance * 10, 1e-9)
    if minimum < -negative_tolerance:
        return KineticSimulationResult(
            status="numerical_failure",
            times=[float(value) for value in solution.t],
            series=_series(compiled.species_ids, values),
            minimumState=minimum,
            maximumConservationDrift=_conservation_drift(
                compiled.stoichiometric_matrix, initial, values
            ),
            functionEvaluations=evaluations,
            message="数值积分产生超过容差的负状态。",
        )
    drift = _conservation_drift(compiled.stoichiometric_matrix, initial, values)
    return KineticSimulationResult(
        status="success",
        times=[float(value) for value in solution.t],
        series=_series(compiled.species_ids, values),
        minimumState=minimum,
        maximumConservationDrift=drift,
        functionEvaluations=evaluations,
        message="数值积分完成。",
    )


def fit_and_compare_models(request: ModelComparisonInput) -> ModelComparisonResult:
    fits = [_fit_model(model, request) for model in request.models]
    eligible = [
        fit
        for fit in fits
        if fit.status == "success" and fit.parameterBasisChangedToFitted
    ]
    selected = min(
        eligible,
        key=lambda item: (
            item.aicc if item.aicc is not None else item.aic if item.aic is not None else math.inf,
            item.residualSumSquares if item.residualSumSquares is not None else math.inf,
            item.modelId,
        ),
        default=None,
    )
    if selected is not None:
        status: ScientificToolStatus = "success"
    elif any(item.status == "numerical_failure" for item in fits):
        status = "numerical_failure"
    else:
        status = "insufficient_data"
    return ModelComparisonResult(
        status=status,
        selectedModelId=None if selected is None else selected.modelId,
        models=fits,
        randomSeed=request.randomSeed,
    )


def _fit_model(
    model: CandidateKineticModel, request: ModelComparisonInput
) -> ModelFitResult:
    parameter_count = len(model.parameters)
    observations = [
        item for item in request.observations if item.speciesId in model.speciesIds
    ]
    if len(observations) <= parameter_count:
        return _fit_failure(
            model,
            "insufficient_data",
            "观测数量不足以支持待拟合参数数量。",
        )
    if set(request.initialAmounts) != set(model.speciesIds):
        return _fit_failure(
            model,
            "invalid_input",
            "初始量必须与候选模型物种完全一致。",
        )
    times = sorted({item.time for item in observations})
    if len(times) < 2:
        return _fit_failure(model, "insufficient_data", "至少需要两个不同时间点。")
    lower = np.array([item.lowerBound for item in model.parameters], dtype=float)
    upper = np.array([item.upperBound for item in model.parameters], dtype=float)
    initial = np.array([item.value for item in model.parameters], dtype=float)
    rng = np.random.default_rng(request.randomSeed)
    starts = [initial]
    for _ in range(request.multiStartCount - 1):
        starts.append(rng.uniform(lower, upper))

    def residuals(values: np.ndarray) -> np.ndarray:
        updated = model.model_copy(
            update={
                "parameters": [
                    parameter.model_copy(update={"value": float(value)})
                    for parameter, value in zip(model.parameters, values, strict=True)
                ]
            }
        )
        simulation = simulate_candidate_kinetics(
            KineticSimulationInput(
                model=updated,
                initialAmounts=request.initialAmounts,
                times=times,
                maximumFunctionEvaluations=request.maximumFunctionEvaluations,
            )
        )
        if simulation.status != "success":
            return np.full(len(observations), 1e6, dtype=float)
        time_index = {time: index for index, time in enumerate(simulation.times)}
        result = []
        for observation in observations:
            predicted = simulation.series[observation.speciesId][time_index[observation.time]]
            scale = observation.standardDeviation or 1.0
            result.append((predicted - observation.value) / scale)
        return np.asarray(result, dtype=float)

    solutions = []
    try:
        for start in starts:
            solutions.append(
                least_squares(
                    residuals,
                    start,
                    bounds=(lower, upper),
                    max_nfev=request.maximumFunctionEvaluations,
                    method="trf",
                )
            )
    except (ValueError, FloatingPointError, OverflowError) as error:
        return _fit_failure(
            model,
            "numerical_failure",
            f"拟合失败：{str(error) or error.__class__.__name__}",
        )
    solution = min(solutions, key=lambda item: (float(np.sum(item.fun**2)), tuple(item.x)))
    if not solution.success or not np.all(np.isfinite(solution.x)):
        return _fit_failure(model, "numerical_failure", "有界最小二乘未收敛。")
    residual_sum = float(np.sum(solution.fun**2))
    observation_count = len(observations)
    degrees_of_freedom = observation_count - parameter_count
    rank = int(np.linalg.matrix_rank(solution.jac))
    singular_values = np.linalg.svd(solution.jac, compute_uv=False)
    identifiable = rank == parameter_count
    condition = None
    if identifiable and singular_values[-1] > 0:
        condition = float(singular_values[0] / singular_values[-1])
        identifiable = condition < 1e10
    aic = _aic(residual_sum, observation_count, parameter_count)
    aicc = (
        aic + (2 * parameter_count * (parameter_count + 1))
        / (observation_count - parameter_count - 1)
        if observation_count > parameter_count + 1
        else None
    )
    return ModelFitResult(
        modelId=model.modelId,
        status="success" if identifiable else "insufficient_data",
        parameters={
            parameter.parameterId: float(value)
            for parameter, value in zip(model.parameters, solution.x, strict=True)
        },
        residualSumSquares=residual_sum,
        degreesOfFreedom=degrees_of_freedom,
        jacobianRank=rank,
        conditionNumber=condition,
        identifiability="identifiable" if identifiable else "unidentifiable",
        aic=aic,
        aicc=aicc,
        calibrationTimeRange=(float(min(times)), float(max(times))),
        parameterBasisChangedToFitted=identifiable,
        message=(
            "拟合收敛且参数在当前数据下可辨识。"
            if identifiable
            else "拟合数值收敛，但参数不可唯一识别。"
        ),
    )


def _fit_failure(
    model: CandidateKineticModel,
    status: ScientificToolStatus,
    message: str,
) -> ModelFitResult:
    return ModelFitResult(
        modelId=model.modelId,
        status=status,
        parameters={item.parameterId: item.value for item in model.parameters},
        residualSumSquares=None,
        degreesOfFreedom=0,
        jacobianRank=None,
        conditionNumber=None,
        identifiability="unidentifiable",
        aic=None,
        aicc=None,
        calibrationTimeRange=None,
        parameterBasisChangedToFitted=False,
        message=message,
    )


def _simulation_failure(
    request: KineticSimulationInput, evaluations: int, message: str
) -> KineticSimulationResult:
    return KineticSimulationResult(
        status="numerical_failure",
        times=[],
        series={species_id: [] for species_id in request.model.speciesIds},
        minimumState=0.0,
        maximumConservationDrift=0.0,
        functionEvaluations=evaluations,
        message=message,
    )


@dataclass(frozen=True, slots=True)
class _CompiledReaction:
    rate_parameter_index: int
    orders: tuple[tuple[int, float], ...]


@dataclass(frozen=True, slots=True)
class _CompiledModel:
    species_ids: tuple[str, ...]
    reactions: tuple[_CompiledReaction, ...]
    stoichiometric_matrix: np.ndarray
    parameter_values: np.ndarray


def _compile_model(model: CandidateKineticModel) -> _CompiledModel:
    species_index = {item: index for index, item in enumerate(model.speciesIds)}
    parameter_index = {
        item.parameterId: index for index, item in enumerate(model.parameters)
    }
    stoichiometry = np.zeros((len(model.speciesIds), len(model.reactions)))
    reactions: list[_CompiledReaction] = []
    for reaction_index, reaction in enumerate(model.reactions):
        for species_id, coefficient in reaction.stoichiometry.items():
            stoichiometry[species_index[species_id], reaction_index] = coefficient
        reactions.append(
            _CompiledReaction(
                rate_parameter_index=parameter_index[reaction.rateConstantParameterId],
                orders=tuple(
                    (species_index[species_id], order)
                    for species_id, order in reaction.orders.items()
                ),
            )
        )
    return _CompiledModel(
        species_ids=tuple(model.speciesIds),
        reactions=tuple(reactions),
        stoichiometric_matrix=stoichiometry,
        parameter_values=np.array([item.value for item in model.parameters], dtype=float),
    )


def _series(species_ids: tuple[str, ...], values: np.ndarray) -> dict[str, list[float]]:
    return {
        species_id: [float(item) for item in values[index]]
        for index, species_id in enumerate(species_ids)
    }


def _conservation_drift(
    stoichiometric_matrix: np.ndarray,
    initial: np.ndarray,
    values: np.ndarray,
) -> float:
    invariants = null_space(stoichiometric_matrix.T)
    if invariants.size == 0:
        return 0.0
    initial_invariants = invariants.T @ initial
    observed = invariants.T @ values
    scale = np.maximum(np.abs(initial_invariants)[:, None], 1.0)
    return float(np.max(np.abs(observed - initial_invariants[:, None]) / scale))


def _aic(residual_sum: float, observations: int, parameters: int) -> float:
    safe_residual = max(residual_sum, np.finfo(float).tiny)
    return float(observations * math.log(safe_residual / observations) + 2 * parameters)
