"""HTTP entry point for the Virtual Reactor API."""

from contextlib import asynccontextmanager
import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from virtual_reactor_api.agent_api import router as agent_router
from virtual_reactor_api.contracts import ReactionSimulationConfig
from virtual_reactor_api.demo_configs import load_ncs_demo_config
from virtual_reactor_api.evaluation_api import router as evaluation_router
from virtual_reactor_api.reaction_depiction import router as chemistry_router
from virtual_reactor_api.campaign_api import router as campaign_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_ncs_demo_config()
    yield


def health() -> dict[str, str]:
    return {"status": "ok"}


def ncs_chlorination_demo_config() -> ReactionSimulationConfig:
    return load_ncs_demo_config()


def parse_cors_origins(value: str | None) -> list[str]:
    if value is None or not value.strip():
        return []

    origins: list[str] = []
    for item in value.split(","):
        origin = item.strip()
        parsed = urlsplit(origin)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("VR_CORS_ORIGINS 包含无效来源。") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError("VR_CORS_ORIGINS 包含无效来源。")
        if origin not in origins:
            origins.append(origin)
    return origins


def create_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    application = FastAPI(
        title="Virtual Reactor API",
        version="0.1.0",
        lifespan=lifespan,
    )
    active_origins = [] if cors_origins is None else cors_origins
    if active_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=active_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )
    application.include_router(agent_router)
    application.include_router(evaluation_router)
    application.include_router(chemistry_router)
    application.include_router(campaign_router)
    application.add_api_route("/health", health, methods=["GET"])
    application.add_api_route(
        "/api/v1/demo-configs/ncs-chlorination",
        ncs_chlorination_demo_config,
        methods=["GET"],
        response_model=ReactionSimulationConfig,
    )
    return application


app = create_app(cors_origins=parse_cors_origins(os.getenv("VR_CORS_ORIGINS")))
