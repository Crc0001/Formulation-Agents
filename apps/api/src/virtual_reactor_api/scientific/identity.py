"""Chemical identity checks derived from explicitly supplied structures."""

from __future__ import annotations

from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors, rdMolDescriptors

from virtual_reactor_api.contracts import StrictModel
from virtual_reactor_api.scientific.contracts import (
    ChemicalIdentityInput,
    FiniteNumber,
    NonBlankText,
    ScientificToolStatus,
)
from virtual_reactor_api.scientific.units import UNIT_REGISTRY


class ChemicalIdentityFinding(StrictModel):
    speciesId: NonBlankText
    name: NonBlankText
    canonicalSmiles: str | None
    derivedFormula: str | None
    averageMolarMass: FiniteNumber | None
    exactMolarMass: FiniteNumber | None
    formalCharge: int | None
    fragmentCount: int | None
    formulaMatches: bool | None
    molarMassMatches: bool | None
    warnings: list[str]


class ChemicalIdentityResult(StrictModel):
    status: ScientificToolStatus
    species: list[ChemicalIdentityFinding]


def inspect_chemical_identity(
    request: ChemicalIdentityInput,
) -> ChemicalIdentityResult:
    findings: list[ChemicalIdentityFinding] = []
    statuses: list[ScientificToolStatus] = []
    for item in request.species:
        if item.smiles is None:
            findings.append(
                ChemicalIdentityFinding(
                    speciesId=item.speciesId,
                    name=item.name,
                    canonicalSmiles=None,
                    derivedFormula=None,
                    averageMolarMass=None,
                    exactMolarMass=None,
                    formalCharge=None,
                    fragmentCount=None,
                    formulaMatches=None,
                    molarMassMatches=None,
                    warnings=["未提供 SMILES，不能从普通名称猜测分子结构。"],
                )
            )
            statuses.append("insufficient_data")
            continue
        with rdBase.BlockLogs():
            molecule = Chem.MolFromSmiles(item.smiles)
        if molecule is None:
            findings.append(
                ChemicalIdentityFinding(
                    speciesId=item.speciesId,
                    name=item.name,
                    canonicalSmiles=None,
                    derivedFormula=None,
                    averageMolarMass=None,
                    exactMolarMass=None,
                    formalCharge=None,
                    fragmentCount=None,
                    formulaMatches=None,
                    molarMassMatches=None,
                    warnings=["SMILES 无法解析，未尝试猜测或替换结构。"],
                )
            )
            statuses.append("invalid_input")
            continue
        canonical = Chem.MolToSmiles(molecule, canonical=True)
        formula = rdMolDescriptors.CalcMolFormula(molecule)
        average_mass = float(Descriptors.MolWt(molecule))
        exact_mass = float(Descriptors.ExactMolWt(molecule))
        formula_matches = None if item.formula is None else item.formula == formula
        mass_matches: bool | None = None
        warnings: list[str] = []
        if formula_matches is False:
            warnings.append(f"输入分子式 {item.formula} 与结构推导值 {formula} 不一致。")
        if item.molarMass is not None:
            try:
                supplied = float(
                    UNIT_REGISTRY.Quantity(
                        item.molarMass.value, item.molarMass.unit
                    ).to("gram / mole").magnitude
                )
                tolerance = max(
                    average_mass * item.molarMassRelativeTolerance,
                    0.1,
                )
                mass_matches = abs(supplied - average_mass) <= tolerance
                if not mass_matches:
                    warnings.append(
                        f"输入摩尔质量 {supplied:g} g/mol 与结构推导值 "
                        f"{average_mass:.6g} g/mol 不一致。"
                    )
            except pint_errors():
                mass_matches = False
                warnings.append("输入摩尔质量单位无法转换为 g/mol。")
        findings.append(
            ChemicalIdentityFinding(
                speciesId=item.speciesId,
                name=item.name,
                canonicalSmiles=canonical,
                derivedFormula=formula,
                averageMolarMass=average_mass,
                exactMolarMass=exact_mass,
                formalCharge=Chem.GetFormalCharge(molecule),
                fragmentCount=len(Chem.GetMolFrags(molecule)),
                formulaMatches=formula_matches,
                molarMassMatches=mass_matches,
                warnings=warnings,
            )
        )
        statuses.append("invalid_input" if formula_matches is False or mass_matches is False else "success")
    return ChemicalIdentityResult(status=_worst_status(statuses), species=findings)


def _worst_status(statuses: list[ScientificToolStatus]) -> ScientificToolStatus:
    for status in ("invalid_input", "insufficient_data", "numerical_failure"):
        if status in statuses:
            return status  # type: ignore[return-value]
    return "success"


def pint_errors() -> tuple[type[Exception], ...]:
    import pint

    return (pint.PintError, ValueError, TypeError)
