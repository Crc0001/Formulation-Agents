"""Versioned, declarative contracts for reaction simulations.

The models in this module intentionally describe data only.  They never accept
executable functions or arbitrary extra fields, so a configuration can be
validated before it reaches a simulation or rendering layer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Id = Annotated[
    str,
    StringConstraints(
        pattern=r"^[a-z][a-z0-9_-]*$",
        strict=True,
    ),
]
NonEmptyString = Annotated[str, StringConstraints(min_length=1, strict=True)]
HexColor = Annotated[
    str,
    StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$", strict=True),
]
StrictFiniteJsonNumber = Annotated[
    float,
    Field(strict=True, allow_inf_nan=False),
]


class StrictModel(BaseModel):
    """Base model that rejects undeclared configuration fields."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Quantity(StrictModel):
    value: StrictFiniteJsonNumber
    unit: NonEmptyString


class PositiveQuantity(Quantity):
    value: Annotated[StrictFiniteJsonNumber, Field(gt=0)]


class RangeSpec(StrictModel):
    minimum: StrictFiniteJsonNumber
    maximum: StrictFiniteJsonNumber

    @model_validator(mode="after")
    def minimum_is_less_than_maximum(self) -> RangeSpec:
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be less than maximum")
        return self


class ParameterBands(StrictModel):
    recommended: RangeSpec
    valid: RangeSpec
    hard: RangeSpec

    @model_validator(mode="after")
    def ranges_are_nested(self) -> ParameterBands:
        if not _range_contains(self.valid, self.recommended):
            raise ValueError("recommended range must be within valid range")
        if not _range_contains(self.hard, self.valid):
            raise ValueError("valid range must be within hard range")
        return self


class SpeciesRole(StrEnum):
    SUBSTRATE = "substrate"
    REAGENT = "reagent"
    INTERMEDIATE = "intermediate"
    PRODUCT = "product"
    SIDE_PRODUCT = "side_product"


class SpeciesSpec(StrictModel):
    id: Id
    name: NonEmptyString
    role: SpeciesRole
    initialAmount: Quantity
    initialAmountControlId: Id | None = None
    color: HexColor


class ContextMaterialRole(StrEnum):
    SOLVENT = "solvent"
    CATALYST = "catalyst"
    ADDITIVE = "additive"
    PROCESSING_AID = "processing_aid"


class ContextMaterialSpec(StrictModel):
    id: Id
    name: NonEmptyString
    role: ContextMaterialRole
    quantity: Quantity | None
    composition: NonEmptyString | None
    purpose: NonEmptyString
    evidenceIds: list[Id] = Field(default_factory=list)


class ExcludedProcessStep(StrictModel):
    position: Literal["before", "after"]
    label: NonEmptyString
    reason: NonEmptyString


class SingleReactionScope(StrictModel):
    kind: Literal["single_reaction_stage"]
    selectedRouteId: Id
    selectedRouteSummary: NonEmptyString
    modeledStage: NonEmptyString
    primarySubstrateId: Id
    targetProductId: Id
    excludedProcessSteps: list[ExcludedProcessStep] = Field(default_factory=list)
    evidenceIds: Annotated[list[Id], Field(min_length=1)]


class MaterialBalanceSpec(StrictModel):
    id: Id
    label: NonEmptyString
    basisSpeciesId: Id
    sourceEquivalentBySpecies: Annotated[
        dict[Id, Annotated[StrictFiniteJsonNumber, Field(gt=0)]],
        Field(min_length=2),
    ]


class SourcedQuantity(StrictModel):
    quantity: Quantity
    basis: Literal["user_supplied", "literature", "derived_teaching"]
    evidenceIds: Annotated[list[Id], Field(min_length=1)]


class ReactionEnthalpySpec(StrictModel):
    reactionId: Id
    enthalpyChangePerAmount: SourcedQuantity


class FeedThermalSpec(StrictModel):
    operationId: Id
    inletTemperature: SourcedQuantity
    heatCapacityPerAmount: SourcedQuantity


class LumpedThermalModel(StrictModel):
    kind: Literal["lumped_energy_balance"]
    initialReactorTemperature: SourcedQuantity
    effectiveHeatCapacity: SourcedQuantity
    jacketTemperatureControlId: Id
    jacketConductance: SourcedQuantity
    maximumCoolingRate: SourcedQuantity
    ambientTemperature: SourcedQuantity | None = None
    ambientConductance: SourcedQuantity | None = None
    reactionEnthalpies: Annotated[
        list[ReactionEnthalpySpec], Field(min_length=1)
    ]
    feedThermalTerms: list[FeedThermalSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def ambient_parameters_are_paired(self) -> LumpedThermalModel:
        if (self.ambientTemperature is None) != (self.ambientConductance is None):
            raise ValueError(
                "ambientTemperature and ambientConductance must be supplied together"
            )
        return self


class ControlSpec(StrictModel):
    id: Id
    label: NonEmptyString
    kind: Literal["slider", "number"]
    unit: NonEmptyString
    default: Quantity
    step: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    bands: ParameterBands
    description: str = ""

    @model_validator(mode="after")
    def default_matches_unit_and_hard_range(self) -> ControlSpec:
        if self.default.unit != self.unit:
            raise ValueError("default unit must match control unit")
        if not _range_includes_value(self.bands.hard, self.default.value):
            raise ValueError("default value must be within the hard range")
        return self


class ApparatusSpec(StrictModel):
    kind: Literal["batch", "semi_batch"]
    basis: Literal["user_supplied", "literature", "derived_teaching"]
    initialLiquidVolume: PositiveQuantity
    defaultFinalLiquidVolume: PositiveQuantity
    maximumModeledLiquidVolume: PositiveQuantity
    nominalVesselVolume: PositiveQuantity
    defaultFillFraction: Annotated[
        StrictFiniteJsonNumber,
        Field(gt=0, le=1),
    ]
    maximumFillFraction: Annotated[
        StrictFiniteJsonNumber,
        Field(gt=0, le=1),
    ]
    geometryStatus: Literal["known", "unknown"]
    thermalCapabilityStatus: Literal["known", "unknown"]
    realEquipmentQualified: bool
    limitations: list[NonEmptyString]

    @model_validator(mode="after")
    def volume_envelope_is_consistent(self) -> ApparatusSpec:
        volumes = (
            self.initialLiquidVolume,
            self.defaultFinalLiquidVolume,
            self.maximumModeledLiquidVolume,
            self.nominalVesselVolume,
        )
        if len({item.unit for item in volumes}) != 1:
            raise ValueError("apparatus volume fields must use one unit")
        if not (
            self.initialLiquidVolume.value
            <= self.defaultFinalLiquidVolume.value
            <= self.maximumModeledLiquidVolume.value
            <= self.nominalVesselVolume.value
        ):
            raise ValueError("apparatus volume envelope must be ordered")
        if self.defaultFillFraction > self.maximumFillFraction:
            raise ValueError(
                "default fill fraction must not exceed maximum fill fraction"
            )
        if self.basis == "derived_teaching" and self.realEquipmentQualified:
            raise ValueError(
                "derived teaching apparatus cannot qualify real equipment"
            )
        return self


class FeedOperation(StrictModel):
    id: Id
    kind: Literal["feed"]
    speciesId: Id
    startMinute: Annotated[StrictFiniteJsonNumber, Field(ge=0)]
    endMinute: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    totalAmount: Quantity
    amountControlId: Id | None = None
    amountReference: (
        Annotated[StrictFiniteJsonNumber, Field(gt=0)] | None
    ) = None
    rateControlId: Id | None = None

    @model_validator(mode="after")
    def feed_timing_and_amount_control_are_valid(self) -> FeedOperation:
        if self.endMinute <= self.startMinute:
            raise ValueError("endMinute must be greater than startMinute")
        if (self.amountControlId is None) != (self.amountReference is None):
            raise ValueError(
                "amountControlId and amountReference must be supplied together"
            )
        return self


class RateModifier(StrictModel):
    controlId: Id | None = None
    processVariableId: Literal["reactor_temperature"] | None = None
    reference: Annotated[
        StrictFiniteJsonNumber,
        Field(
            description=(
                "Reference value expressed in the referenced control's declared unit."
            )
        ),
    ]
    coefficient: Annotated[
        StrictFiniteJsonNumber,
        Field(
            description=(
                "Coefficient expressed in the reciprocal of the referenced "
                "control's unit."
            )
        ),
    ]
    minimumFactor: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    maximumFactor: Annotated[StrictFiniteJsonNumber, Field(gt=0)]

    @model_validator(mode="after")
    def factor_range_is_ordered(self) -> RateModifier:
        if (self.controlId is None) == (self.processVariableId is None):
            raise ValueError(
                "exactly one of controlId or processVariableId is required"
            )
        if self.minimumFactor > self.maximumFactor:
            raise ValueError("minimumFactor must not exceed maximumFactor")
        return self


class ReactionEdge(StrictModel):
    id: Id
    label: NonEmptyString
    kind: Literal["mass_action"]
    stoichiometry: dict[Id, StrictFiniteJsonNumber]
    orders: dict[Id, StrictFiniteJsonNumber]
    rateConstantPerMinute: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    normalizationAmount: PositiveQuantity
    modifiers: list[RateModifier] = Field(default_factory=list)
    pathway: Literal["main", "side"]
    mechanismSummary: NonEmptyString
    modelBasis: Literal["literature", "analogy", "derived_teaching"]
    evidenceIds: list[Id]


class ObservableSpec(StrictModel):
    id: Id
    label: NonEmptyString
    kind: Literal["species_fraction", "conversion", "selectivity"]
    speciesId: Id | None = None
    unit: NonEmptyString


class PresentationSpec(StrictModel):
    chartIds: list[Id]
    animationIds: list[Id]


class AnnotationTrigger(StrictModel):
    kind: Literal["time", "species_fraction", "control_outside_recommended"]
    targetId: Id | None = None
    operator: Literal["gte", "lte"] = "gte"
    value: StrictFiniteJsonNumber


class AnnotationSpec(StrictModel):
    id: Id
    severity: Literal["info", "attention", "warning", "critical"]
    scope: Literal["simulation", "real_world_operation"]
    simulationEffect: Literal["none", "block_start"]
    title: NonEmptyString
    body: NonEmptyString
    trigger: AnnotationTrigger
    evidenceIds: list[Id] = Field(default_factory=list)

    @model_validator(mode="after")
    def real_world_scope_never_blocks_simulation(self) -> AnnotationSpec:
        if (
            self.scope == "real_world_operation"
            and self.simulationEffect != "none"
        ):
            raise ValueError(
                "real_world_operation annotation must not block simulation"
            )
        return self


class EvidenceSpec(StrictModel):
    id: Id
    kind: Literal["literature", "analogy", "demo_assumption"]
    citation: NonEmptyString
    supports: list[NonEmptyString]


class ConfidenceSpec(StrictModel):
    level: Literal["low", "medium", "high"]
    summary: NonEmptyString


class ReactionEquationSpec(StrictModel):
    """A complete reaction equation suitable for deterministic 2D depiction."""

    id: Id
    role: Literal["simulated", "explanatory"]
    title: NonEmptyString
    reactionSmiles: NonEmptyString
    conditions: list[NonEmptyString] = Field(default_factory=list)
    evidenceIds: list[Id] = Field(default_factory=list)


class ReactionSpec(StrictModel):
    className: NonEmptyString
    summary: NonEmptyString
    equation: ReactionEquationSpec | None = None

    @model_validator(mode="after")
    def equation_describes_the_simulated_reaction(self) -> ReactionSpec:
        if self.equation is not None and self.equation.role != "simulated":
            raise ValueError("config reaction equation role must be simulated")
        return self


class SimulationSpec(StrictModel):
    endMinute: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    stepMinute: Annotated[StrictFiniteJsonNumber, Field(gt=0)]
    endMinuteControlId: Id | None = None


class ReactionSimulationConfig(StrictModel):
    schemaVersion: Literal["1.5.0"]
    configId: Id
    title: NonEmptyString
    scope: SingleReactionScope
    materialBalance: MaterialBalanceSpec
    thermalModel: LumpedThermalModel | None
    reaction: ReactionSpec
    simulation: SimulationSpec
    species: list[SpeciesSpec]
    contextMaterials: list[ContextMaterialSpec]
    apparatus: ApparatusSpec
    controls: list[ControlSpec]
    operations: list[FeedOperation]
    reactions: list[ReactionEdge]
    observables: list[ObservableSpec]
    presentation: PresentationSpec
    annotations: list[AnnotationSpec]
    evidence: list[EvidenceSpec]
    confidence: ConfidenceSpec


def _range_contains(container: RangeSpec, contained: RangeSpec) -> bool:
    return (
        container.minimum <= contained.minimum
        and contained.maximum <= container.maximum
    )


def _range_includes_value(
    range_spec: RangeSpec,
    value: StrictFiniteJsonNumber,
) -> bool:
    return range_spec.minimum <= value <= range_spec.maximum
