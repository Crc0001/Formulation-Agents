"""Deterministic parameter-identifiability checks."""

from __future__ import annotations

import numpy as np

from virtual_reactor_api.contracts import StrictModel
from virtual_reactor_api.scientific.contracts import (
    FiniteNumber,
    IdentifiabilityInput,
    IdentifiabilityVerdict,
    NonBlankText,
    ScientificToolStatus,
)


class IdentifiabilityResult(StrictModel):
    status: ScientificToolStatus
    verdict: IdentifiabilityVerdict
    parameterCount: int
    independentObservationCount: int
    jacobianRank: int | None
    singularValues: list[FiniteNumber]
    conditionNumber: FiniteNumber | None
    unresolvedParameterIds: list[NonBlankText]
    warnings: list[NonBlankText]


def assess_parameter_identifiability(
    request: IdentifiabilityInput,
) -> IdentifiabilityResult:
    parameter_ids = [item.parameterId for item in request.model.parameters]
    parameter_count = len(parameter_ids)
    observation_count = len(request.observations)
    if observation_count < parameter_count:
        return IdentifiabilityResult(
            status="insufficient_data",
            verdict="unidentifiable",
            parameterCount=parameter_count,
            independentObservationCount=observation_count,
            jacobianRank=None,
            singularValues=[],
            conditionNumber=None,
            unresolvedParameterIds=parameter_ids,
            warnings=["独立观测数量少于待识别参数数量，参数不可唯一识别。"],
        )
    if request.sensitivityMatrix is None:
        return IdentifiabilityResult(
            status="insufficient_data",
            verdict="unidentifiable",
            parameterCount=parameter_count,
            independentObservationCount=observation_count,
            jacobianRank=None,
            singularValues=[],
            conditionNumber=None,
            unresolvedParameterIds=parameter_ids,
            warnings=["缺少灵敏度矩阵，不能证明参数可唯一识别。"],
        )
    matrix = np.asarray(request.sensitivityMatrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape != (observation_count, parameter_count):
        return IdentifiabilityResult(
            status="invalid_input",
            verdict="unidentifiable",
            parameterCount=parameter_count,
            independentObservationCount=observation_count,
            jacobianRank=None,
            singularValues=[],
            conditionNumber=None,
            unresolvedParameterIds=parameter_ids,
            warnings=[
                "灵敏度矩阵形状必须为观测数量乘以参数数量。"
            ],
        )
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    largest = float(singular_values[0]) if singular_values.size else 0.0
    absolute_tolerance = request.relativeTolerance * max(largest, 1.0)
    rank = int(np.linalg.matrix_rank(matrix, tol=absolute_tolerance))
    unresolved = _unresolved_parameters(
        matrix, parameter_ids, rank, request.relativeTolerance
    )
    if rank < parameter_count:
        return IdentifiabilityResult(
            status="insufficient_data",
            verdict="unidentifiable",
            parameterCount=parameter_count,
            independentObservationCount=observation_count,
            jacobianRank=rank,
            singularValues=[float(value) for value in singular_values],
            conditionNumber=None,
            unresolvedParameterIds=unresolved or parameter_ids,
            warnings=["灵敏度矩阵降秩，至少一组参数效应无法区分。"],
        )
    smallest = float(singular_values[-1])
    condition_number = largest / smallest
    weak = condition_number > 1.0 / request.relativeTolerance
    return IdentifiabilityResult(
        status="success",
        verdict="partially_identifiable" if weak else "identifiable",
        parameterCount=parameter_count,
        independentObservationCount=observation_count,
        jacobianRank=rank,
        singularValues=[float(value) for value in singular_values],
        conditionNumber=condition_number,
        unresolvedParameterIds=[] if not weak else parameter_ids,
        warnings=(
            ["灵敏度矩阵条件数过高，参数估计可能不稳定。"] if weak else []
        ),
    )


def _unresolved_parameters(
    matrix: np.ndarray,
    parameter_ids: list[str],
    rank: int,
    relative_tolerance: float,
) -> list[str]:
    _, _, right_vectors = np.linalg.svd(matrix, full_matrices=True)
    null_vectors = right_vectors[rank:]
    if null_vectors.size == 0:
        return []
    weights = np.max(np.abs(null_vectors), axis=0)
    threshold = max(relative_tolerance, float(np.max(weights)) * relative_tolerance)
    return [
        parameter_id
        for parameter_id, weight in zip(parameter_ids, weights, strict=True)
        if float(weight) > threshold
    ]
