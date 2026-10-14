"""Compatibility wrapper for structured deterministic candidate preflight."""

from __future__ import annotations

from virtual_reactor_api.agent_models import CandidateReactionConfig
from virtual_reactor_api.agent_preflight import validate_candidate_preflight


def validate_candidate_executability(
    candidate: CandidateReactionConfig,
) -> tuple[bool, list[str]]:
    report = validate_candidate_preflight(candidate)
    return report.executable, [issue.message for issue in report.issues]
