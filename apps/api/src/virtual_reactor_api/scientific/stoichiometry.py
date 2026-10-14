"""Element balance, stoichiometric rank, and limiting-reagent analysis."""

from __future__ import annotations

import re

import numpy as np
import sympy as sp
from pydantic import Field
from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors

from virtual_reactor_api.contracts import StrictModel
from virtual_reactor_api.scientific.contracts import (
    FiniteNumber,
    NonBlankText,
    ScientificToolStatus,
    StoichiometryAnalysisInput,
)


_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)")


class ReactionBalanceFinding(StrictModel):
    reactionId: NonBlankText
    balanced: bool
    elementResiduals: dict[str, FiniteNumber]


class StoichiometryAnalysisResult(StrictModel):
    status: ScientificToolStatus
    balanced: bool
    elements: list[str]
    reactions: list[ReactionBalanceFinding]
    matrixRank: int = Field(ge=0)
    dependentReactionIds: list[str]
    limitingSpeciesIds: list[str]
    maximumExtent: FiniteNumber | None
    excessCapacityRatios: dict[str, FiniteNumber]
    invalidSpeciesIds: list[str]


def analyze_stoichiometry(
    request: StoichiometryAnalysisInput,
) -> StoichiometryAnalysisResult:
    compositions: dict[str, dict[str, int]] = {}
    invalid_species: list[str] = []
    for species in request.species:
        formula = species.formula
        if species.smiles is not None:
            with rdBase.BlockLogs():
                molecule = Chem.MolFromSmiles(species.smiles)
            if molecule is None:
                invalid_species.append(species.speciesId)
                continue
            formula = rdMolDescriptors.CalcMolFormula(molecule)
        parsed = _parse_formula(formula or "")
        if parsed is None:
            invalid_species.append(species.speciesId)
            continue
        compositions[species.speciesId] = parsed

    if invalid_species:
        return StoichiometryAnalysisResult(
            status="invalid_input",
            balanced=False,
            elements=[],
            reactions=[],
            matrixRank=0,
            dependentReactionIds=[],
            limitingSpeciesIds=[],
            maximumExtent=None,
            excessCapacityRatios={},
            invalidSpeciesIds=invalid_species,
        )

    species_ids = [item.speciesId for item in request.species]
    reaction_ids = [item.reactionId for item in request.reactions]
    elements = sorted(
        {element for composition in compositions.values() for element in composition}
    )
    element_matrix = np.array(
        [
            [compositions[species_id].get(element, 0) for species_id in species_ids]
            for element in elements
        ],
        dtype=float,
    )
    stoichiometric_matrix = np.array(
        [
            [reaction.stoichiometry.get(species_id, 0.0) for reaction in request.reactions]
            for species_id in species_ids
        ],
        dtype=float,
    )
    residual_matrix = element_matrix @ stoichiometric_matrix
    findings: list[ReactionBalanceFinding] = []
    for column, reaction in enumerate(request.reactions):
        residuals = {
            element: _clean_zero(float(residual_matrix[row, column]), request.residualTolerance)
            for row, element in enumerate(elements)
        }
        findings.append(
            ReactionBalanceFinding(
                reactionId=reaction.reactionId,
                balanced=all(abs(value) <= request.residualTolerance for value in residuals.values()),
                elementResiduals=residuals,
            )
        )
    rank = int(np.linalg.matrix_rank(stoichiometric_matrix))
    _, pivots = sp.Matrix(stoichiometric_matrix).rref()
    dependent = [
        reaction_id
        for index, reaction_id in enumerate(reaction_ids)
        if index not in set(pivots)
    ]
    limiting, extent, capacity_ratios = _limiting_reagent(request)
    balanced = all(item.balanced for item in findings)
    return StoichiometryAnalysisResult(
        status="success" if balanced else "invalid_input",
        balanced=balanced,
        elements=elements,
        reactions=findings,
        matrixRank=rank,
        dependentReactionIds=dependent,
        limitingSpeciesIds=limiting,
        maximumExtent=extent,
        excessCapacityRatios=capacity_ratios,
        invalidSpeciesIds=[],
    )


def _parse_formula(formula: str) -> dict[str, int] | None:
    if not formula:
        return None
    position = 0
    composition: dict[str, int] = {}
    for match in _FORMULA_TOKEN.finditer(formula):
        if match.start() != position:
            return None
        element, count_text = match.groups()
        count = int(count_text) if count_text else 1
        if count <= 0:
            return None
        composition[element] = composition.get(element, 0) + count
        position = match.end()
    return composition if position == len(formula) and composition else None


def _limiting_reagent(
    request: StoichiometryAnalysisInput,
) -> tuple[list[str], float | None, dict[str, float]]:
    if len(request.reactions) != 1:
        return [], None, {}
    reaction = request.reactions[0]
    amount_by_species = {
        species.speciesId: species.initialAmount for species in request.species
    }
    capacities: dict[str, float] = {}
    for species_id, coefficient in reaction.stoichiometry.items():
        if coefficient >= 0:
            continue
        amount = amount_by_species.get(species_id)
        if amount is None:
            return [], None, {}
        capacities[species_id] = amount / -coefficient
    if not capacities:
        return [], None, {}
    maximum_extent = min(capacities.values())
    tolerance = max(1e-12, abs(maximum_extent) * 1e-9)
    limiting = sorted(
        species_id
        for species_id, capacity in capacities.items()
        if abs(capacity - maximum_extent) <= tolerance
    )
    ratios = {
        species_id: (capacity / maximum_extent if maximum_extent > 0 else 1.0)
        for species_id, capacity in capacities.items()
    }
    return limiting, maximum_extent, ratios


def _clean_zero(value: float, tolerance: float) -> float:
    return 0.0 if abs(value) <= tolerance else value
