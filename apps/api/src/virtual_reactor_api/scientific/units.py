"""Unit and dimensionality validation using one configured Pint registry."""

from __future__ import annotations

from typing import Literal

import pint
from pydantic import Field

from virtual_reactor_api.contracts import StrictModel
from virtual_reactor_api.scientific.contracts import (
    FiniteNumber,
    NonBlankText,
    QuantityDimension,
    QuantityValidationInput,
    ScientificToolStatus,
)


UNIT_REGISTRY = pint.UnitRegistry(autoconvert_offset_to_baseunit=False)

_REFERENCE_UNITS: dict[QuantityDimension, str] = {
    "amount": "mole",
    "mass": "gram",
    "volume": "liter",
    "concentration": "mole / liter",
    "temperature": "kelvin",
    "temperature_delta": "delta_kelvin",
    "pressure": "pascal",
    "time": "second",
    "rate": "mole / second",
    "dimensionless": "dimensionless",
}


class ValidatedQuantity(StrictModel):
    quantityId: NonBlankText
    sourceValue: FiniteNumber
    sourceUnit: NonBlankText
    expectedDimension: QuantityDimension
    convertedValue: FiniteNumber | None
    targetUnit: NonBlankText
    error: str | None


class QuantityValidationResult(StrictModel):
    status: ScientificToolStatus
    quantities: list[ValidatedQuantity]


def validate_quantities_and_units(
    request: QuantityValidationInput,
) -> QuantityValidationResult:
    results: list[ValidatedQuantity] = []
    for item in request.quantities:
        converted: float | None = None
        error: str | None = None
        try:
            _validate_temperature_kind(
                item.expectedDimension, item.unit, item.targetUnit
            )
            source = UNIT_REGISTRY.Quantity(item.value, item.unit)
            reference = UNIT_REGISTRY.Quantity(1, _REFERENCE_UNITS[item.expectedDimension])
            if source.dimensionality != reference.dimensionality:
                raise ValueError(
                    f"单位 {item.unit} 与期望量纲 {item.expectedDimension} 不兼容"
                )
            converted = float(source.to(item.targetUnit).magnitude)
        except (pint.PintError, ValueError, TypeError) as exception:
            error = str(exception) or "单位无法转换"
        results.append(
            ValidatedQuantity(
                quantityId=item.quantityId,
                sourceValue=item.value,
                sourceUnit=item.unit,
                expectedDimension=item.expectedDimension,
                convertedValue=converted,
                targetUnit=item.targetUnit,
                error=error,
            )
        )
    return QuantityValidationResult(
        status=(
            "success"
            if all(item.error is None for item in results)
            else "invalid_input"
        ),
        quantities=results,
    )


def _validate_temperature_kind(
    dimension: QuantityDimension, source_unit: str, target_unit: str
) -> None:
    source_is_delta = source_unit.lower().startswith("delta_")
    target_is_delta = target_unit.lower().startswith("delta_")
    if dimension == "temperature_delta" and not (
        source_is_delta and target_is_delta
    ):
        raise ValueError("温差必须使用 delta_ 温度单位")
    if dimension == "temperature" and (source_is_delta or target_is_delta):
        raise ValueError("绝对温度不能使用温差单位")

