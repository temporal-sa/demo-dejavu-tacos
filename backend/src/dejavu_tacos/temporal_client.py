from __future__ import annotations

import os
from typing import Any

from temporalio.client import Client


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_TASK_QUEUE = "dejavu-tacos"


def temporal_task_queue() -> str:
    return os.environ.get("TEMPORAL_TASK_QUEUE") or DEFAULT_TASK_QUEUE


def temporal_target_host() -> str:
    return (
        os.environ.get("TEMPORAL_ENDPOINT")
        or os.environ.get("TEMPORAL_ADDRESS")
        or "localhost:7233"
    )


async def connect_temporal_client() -> Client:
    api_key = os.environ.get("TEMPORAL_API_KEY")
    client_config: dict[str, Any] = {
        "namespace": os.environ.get("TEMPORAL_NAMESPACE", "default"),
        "tls": _env_flag("TEMPORAL_TLS", default=bool(api_key)),
    }
    if api_key:
        client_config["api_key"] = api_key

    return await Client.connect(temporal_target_host(), **client_config)
