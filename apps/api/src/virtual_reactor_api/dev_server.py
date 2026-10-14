"""Environment-driven Uvicorn entry point for local development."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

import uvicorn


@dataclass(frozen=True, slots=True)
class DevServerSettings:
    host: str
    port: int
    reload: bool

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> "DevServerSettings":
        active = os.environ if environment is None else environment
        host = active.get("VR_API_HOST", "0.0.0.0").strip()
        if not host:
            raise ValueError("VR_API_HOST 不能为空。")
        return cls(
            host=host,
            port=_parse_tcp_port(active.get("VR_API_PORT", "18000")),
            reload=_parse_reload(active.get("VR_API_RELOAD", "1")),
        )


def _parse_tcp_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("VR_API_PORT 必须是 1 至 65535 的整数。") from error
    if not 1 <= port <= 65535:
        raise ValueError("VR_API_PORT 必须是 1 至 65535 的整数。")
    return port


def _parse_reload(value: str) -> bool:
    # 某些沙箱环境下 reloader 子进程的出站连接会失效，VR_API_RELOAD=0 可退回单进程模式。
    return value.strip().lower() not in {"0", "false", "no", "off"}


def main() -> None:
    settings = DevServerSettings.from_environment()
    uvicorn.run(
        "virtual_reactor_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
