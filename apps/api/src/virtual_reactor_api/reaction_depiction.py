"""Validated RDKit reaction parsing and deterministic SVG depiction."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import StringConstraints
from rdkit import rdBase
from rdkit.Chem import rdChemReactions
from rdkit.Chem.Draw import rdMolDraw2D
from typing import Annotated

from virtual_reactor_api.contracts import StrictModel


ReactionSmiles = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]


class ReactionDepictionRequest(StrictModel):
    reactionSmiles: ReactionSmiles


router = APIRouter(prefix="/api/v1/chemistry", tags=["chemistry"])


def parse_reaction_smiles(reaction_smiles: str) -> rdChemReactions.ChemicalReaction:
    """Parse a complete Reaction SMILES without guessing missing reaction sides."""

    parts = reaction_smiles.split(">")
    if len(parts) != 3 or not parts[0].strip() or not parts[2].strip():
        raise ValueError("missing_reaction_side")

    with rdBase.BlockLogs():
        try:
            reaction = rdChemReactions.ReactionFromSmarts(
                reaction_smiles,
                useSmiles=True,
            )
        except (ValueError, RuntimeError):
            reaction = None
    if reaction is None:
        raise ValueError("invalid_reaction_smiles")
    if reaction.GetNumReactantTemplates() == 0 or reaction.GetNumProductTemplates() == 0:
        raise ValueError("missing_reaction_side")
    return reaction


def depict_reaction_svg(reaction_smiles: str) -> str:
    reaction = parse_reaction_smiles(reaction_smiles)
    drawer = rdMolDraw2D.MolDraw2DSVG(1200, 280)
    drawer.DrawReaction(reaction)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


@router.post("/reaction-depictions", response_class=Response)
def create_reaction_depiction(payload: ReactionDepictionRequest) -> Response:
    try:
        svg = depict_reaction_svg(payload.reactionSmiles)
    except ValueError as error:
        if str(error) == "missing_reaction_side":
            detail = "请输入同时包含反应物和产物的 Reaction SMILES。"
        else:
            detail = "Reaction SMILES 无法解析，请检查结构和反应箭头。"
        raise HTTPException(status_code=422, detail=detail) from error
    return Response(content=svg, media_type="image/svg+xml")
