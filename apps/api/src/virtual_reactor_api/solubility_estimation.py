"""Structure-based solubility baseline with explicit extrapolation labels."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SolubilityEstimate:
    value_log10_mol_l: float
    interval_log10_mol_l: tuple[float, float]
    solvent: str
    basis: str
    confidence: str


def estimate_esol_baseline(*, logp: float, molecular_weight: float,
                           rotatable_bonds: int, aromatic_proportion: float) -> SolubilityEstimate:
    """Delaney-style aqueous baseline; coefficients are not solvent-specific."""
    if molecular_weight <= 0 or rotatable_bonds < 0 or not 0 <= aromatic_proportion <= 1:
        raise ValueError("invalid molecular descriptors")
    value = 0.16 - 1.5 * logp - 0.01 * (molecular_weight - 40) + 0.066 * rotatable_bonds + 0.066 * aromatic_proportion
    return SolubilityEstimate(value, (value - 0.9, value + 0.9), "water", "Delaney ESOL structure baseline", "low")


def estimate_from_smiles(smiles: str) -> SolubilityEstimate:
    """Calculate descriptors with RDKit; fail closed when structure is invalid."""
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        raise ValueError("invalid SMILES")
    heavy = Descriptors.HeavyAtomCount(molecule)
    aromatic = sum(atom.GetIsAromatic() for atom in molecule.GetAtoms())
    return estimate_esol_baseline(
        logp=Crippen.MolLogP(molecule),
        molecular_weight=Descriptors.MolWt(molecule),
        rotatable_bonds=Lipinski.NumRotatableBonds(molecule),
        aromatic_proportion=aromatic / heavy if heavy else 0,
    )
