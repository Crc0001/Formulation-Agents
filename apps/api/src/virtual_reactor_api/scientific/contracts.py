"""Strict contracts shared by deterministic scientific tools."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from virtual_reactor_api.contracts import StrictModel


NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]
PositiveFiniteNumber = Annotated[float, Field(gt=0, allow_inf_nan=False)]
ScientificToolStatus = Literal[
    "success", "invalid_input", "insufficient_data", "numerical_failure"
]
ParameterBasis = Literal["measured", "literature", "derived", "assumed", "fitted"]
IdentifiabilityVerdict = Literal[
    "identifiable", "partially_identifiable", "unidentifiable"
]
QuantityDimension = Literal[
    "amount",
    "mass",
    "volume",
    "concentration",
    "temperature",
    "temperature_delta",
    "pressure",
    "time",
    "rate",
    "dimensionless",
]


class ScalarQuantity(StrictModel):
    value: FiniteNumber
    unit: NonBlankText


class ChemicalSpeciesInput(StrictModel):
    speciesId: NonBlankText
    name: NonBlankText
    smiles: NonBlankText | None = None
    formula: NonBlankText | None = None
    molarMass: ScalarQuantity | None = None
    molarMassRelativeTolerance: Annotated[
        float, Field(gt=0, allow_inf_nan=False)
    ] = 0.02


class ChemicalIdentityInput(StrictModel):
    species: Annotated[list[ChemicalSpeciesInput], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_species(self) -> "ChemicalIdentityInput":
        _require_unique([item.speciesId for item in self.species], "speciesId")
        return self


class QuantityInput(StrictModel):
    quantityId: NonBlankText
    value: FiniteNumber
    unit: NonBlankText
    expectedDimension: QuantityDimension
    targetUnit: NonBlankText


class QuantityValidationInput(StrictModel):
    quantities: Annotated[list[QuantityInput], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_quantities(self) -> "QuantityValidationInput":
        _require_unique([item.quantityId for item in self.quantities], "quantityId")
        return self


class StoichiometricSpeciesInput(StrictModel):
    speciesId: NonBlankText
    formula: NonBlankText | None = None
    smiles: NonBlankText | None = None
    initialAmount: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def require_identity(self) -> "StoichiometricSpeciesInput":
        if self.formula is None and self.smiles is None:
            raise ValueError("stoichiometric species requires formula or smiles")
        return self


class StoichiometricReactionInput(StrictModel):
    reactionId: NonBlankText
    stoichiometry: Annotated[dict[str, FiniteNumber], Field(min_length=1)]

    @field_validator("stoichiometry")
    @classmethod
    def reject_zero_stoichiometry(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        if all(coefficient == 0 for coefficient in value.values()):
            raise ValueError("stoichiometry cannot contain only zeros")
        return value


class StoichiometryAnalysisInput(StrictModel):
    species: Annotated[
        list[StoichiometricSpeciesInput], Field(min_length=1)
    ]
    reactions: Annotated[
        list[StoichiometricReactionInput], Field(min_length=1)
    ]
    residualTolerance: Annotated[
        float, Field(gt=0, allow_inf_nan=False)
    ] = 1e-9

    @model_validator(mode="after")
    def validate_references(self) -> "StoichiometryAnalysisInput":
        species_ids = [item.speciesId for item in self.species]
        reaction_ids = [item.reactionId for item in self.reactions]
        _require_unique(species_ids, "speciesId")
        _require_unique(reaction_ids, "reactionId")
        known = set(species_ids)
        for reaction in self.reactions:
            unknown = set(reaction.stoichiometry) - known
            if unknown:
                raise ValueError(f"reaction references unknown species: {sorted(unknown)}")
        return self


class KineticParameter(StrictModel):
    parameterId: NonBlankText
    value: FiniteNumber
    lowerBound: FiniteNumber
    upperBound: FiniteNumber
    unit: NonBlankText
    basis: ParameterBasis

    @model_validator(mode="after")
    def validate_bounds(self) -> "KineticParameter":
        if self.lowerBound >= self.upperBound:
            raise ValueError("parameter bounds must be ordered")
        if not self.lowerBound <= self.value <= self.upperBound:
            raise ValueError("parameter value must be inside bounds")
        return self


class CandidateReaction(StrictModel):
    reactionId: NonBlankText
    stoichiometry: Annotated[dict[str, FiniteNumber], Field(min_length=1)]
    orders: Annotated[dict[str, FiniteNumber], Field(min_length=1)]
    rateConstantParameterId: NonBlankText

    @field_validator("stoichiometry")
    @classmethod
    def require_reactant_and_product(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        if not any(item < 0 for item in value.values()) or not any(
            item > 0 for item in value.values()
        ):
            raise ValueError("reaction requires reactant and product coefficients")
        return value

    @field_validator("orders")
    @classmethod
    def reject_negative_orders(cls, value: dict[str, float]) -> dict[str, float]:
        if any(item < 0 for item in value.values()):
            raise ValueError("reaction orders must be non-negative")
        return value


class CandidateKineticModel(StrictModel):
    modelId: NonBlankText
    speciesIds: Annotated[list[NonBlankText], Field(min_length=1)]
    reactions: Annotated[list[CandidateReaction], Field(min_length=1)]
    parameters: Annotated[list[KineticParameter], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_references(self) -> "CandidateKineticModel":
        _require_unique(self.speciesIds, "speciesId")
        _require_unique([item.reactionId for item in self.reactions], "reactionId")
        parameter_ids = [item.parameterId for item in self.parameters]
        _require_unique(parameter_ids, "parameterId")
        known_species = set(self.speciesIds)
        known_parameters = set(parameter_ids)
        for reaction in self.reactions:
            unknown_species = (
                set(reaction.stoichiometry) | set(reaction.orders)
            ) - known_species
            if unknown_species:
                raise ValueError(
                    f"reaction references unknown species: {sorted(unknown_species)}"
                )
            if reaction.rateConstantParameterId not in known_parameters:
                raise ValueError(
                    "reaction references unknown parameter: "
                    f"{reaction.rateConstantParameterId}"
                )
        return self


class Observation(StrictModel):
    observationId: NonBlankText
    time: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    speciesId: NonBlankText
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    standardDeviation: PositiveFiniteNumber | None = None


class IdentifiabilityInput(StrictModel):
    model: CandidateKineticModel
    observations: Annotated[list[Observation], Field(min_length=1)]
    sensitivityMatrix: list[list[FiniteNumber]] | None = None
    relativeTolerance: Annotated[
        float, Field(gt=0, allow_inf_nan=False)
    ] = 1e-8

    @model_validator(mode="after")
    def validate_observation_species(self) -> "IdentifiabilityInput":
        unknown = {item.speciesId for item in self.observations} - set(
            self.model.speciesIds
        )
        if unknown:
            raise ValueError(f"observations reference unknown species: {sorted(unknown)}")
        return self


class KineticSimulationInput(StrictModel):
    model: CandidateKineticModel
    initialAmounts: dict[str, Annotated[float, Field(ge=0, allow_inf_nan=False)]]
    times: Annotated[list[Annotated[float, Field(ge=0, allow_inf_nan=False)]], Field(min_length=2)]
    relativeTolerance: Annotated[float, Field(gt=0)] = 1e-7
    absoluteTolerance: Annotated[float, Field(gt=0)] = 1e-9
    maximumStep: PositiveFiniteNumber | None = None
    maximumFunctionEvaluations: Annotated[int, Field(gt=0)] = 100_000

    @model_validator(mode="after")
    def validate_grid_and_amounts(self) -> "KineticSimulationInput":
        if any(right <= left for left, right in zip(self.times, self.times[1:])):
            raise ValueError("times must be strictly increasing")
        if set(self.initialAmounts) != set(self.model.speciesIds):
            raise ValueError("initialAmounts must contain every model species exactly once")
        return self


class ModelComparisonInput(StrictModel):
    models: Annotated[list[CandidateKineticModel], Field(min_length=1)]
    initialAmounts: dict[str, Annotated[float, Field(ge=0, allow_inf_nan=False)]]
    observations: Annotated[list[Observation], Field(min_length=1)]
    randomSeed: int = 0
    maximumFunctionEvaluations: Annotated[int, Field(gt=0)] = 10_000
    multiStartCount: Annotated[int, Field(ge=1)] = 3

    @model_validator(mode="after")
    def validate_model_ids(self) -> "ModelComparisonInput":
        _require_unique([item.modelId for item in self.models], "modelId")
        return self


class ScientificToolReceipt(StrictModel):
    toolCallId: NonBlankText
    toolName: NonBlankText
    toolVersion: Literal["1.0.0"] = "1.0.0"
    status: ScientificToolStatus
    normalizedInput: dict[str, Any]
    result: dict[str, Any]
    warnings: list[NonBlankText]
    assumptions: list[NonBlankText]
    applicability: list[NonBlankText]
    durationMs: Annotated[int, Field(ge=0)]
    randomSeed: int
    libraryVersions: dict[str, NonBlankText]
    artifactPath: NonBlankText

    @field_validator("artifactPath")
    @classmethod
    def require_safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or ":" in value or "\\" in value:
            raise ValueError("artifactPath must be a safe relative path")
        return value


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")
