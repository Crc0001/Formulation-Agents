"""Validated demonstration configurations shipped with the API."""

from functools import lru_cache
from importlib import resources

from virtual_reactor_api.contracts import ReactionSimulationConfig


@lru_cache
def _ncs_demo_config_json() -> str:
    return (
        resources.files("virtual_reactor_api.data")
        .joinpath("ncs-chlorination.v1.json")
        .read_text(encoding="utf-8")
    )


def load_ncs_demo_config() -> ReactionSimulationConfig:
    """Return a fresh, validated NCS demonstration configuration model."""

    return ReactionSimulationConfig.model_validate_json(
        _ncs_demo_config_json()
    )
