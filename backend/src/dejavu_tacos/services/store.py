from __future__ import annotations

import asyncio
import os

import aiohttp

from dejavu_tacos import config
from dejavu_tacos.config import should_fail

_BACKEND_URL = os.environ.get("DEJAVU_BACKEND_URL", "")


class StoreError(Exception):
    pass


async def _check_should_fail(step: str, order_id: str = "") -> bool:
    """Check failure state via backend API (external) or local config (in-process).

    order_id lets the backend resolve which browser session gates this order, so
    store connectivity is evaluated per-session rather than globally."""
    if _BACKEND_URL:
        try:
            params = {"order_id": order_id} if order_id else None
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{_BACKEND_URL}/api/internal/should-fail/{step}", params=params
                ) as resp:
                    data = await resp.json()
                    return data.get("should_fail", False)
        except Exception:
            return False
    return should_fail(step, config.order_sessions.get(order_id))


async def _register_store_order(order_id: str, order_data: dict) -> None:
    """Register order on KDS via backend API (external) or local config (in-process)."""
    if _BACKEND_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{_BACKEND_URL}/api/internal/store-orders/{order_id}",
                    json=order_data,
                ) as resp:
                    resp.raise_for_status()
        except Exception:
            pass
    else:
        config.store_orders[order_id] = order_data


async def validate_store(store_id: str = "store-001") -> dict:
    """Check that the store is open and accepting orders."""
    await asyncio.sleep(0.3)
    if await _check_should_fail("validate_store"):
        raise StoreError("Unable to reach store — connection refused")
    return {
        "store_id": store_id,
        "open": True,
        "name": "Déjà Vu Tacos #42",
        "estimated_wait_minutes": 12,
    }


async def submit_to_store(order_id: str, items: list[dict]) -> dict:
    """Submit the order to the store's kitchen system."""
    await asyncio.sleep(0.5)
    if await _check_should_fail("submit_to_store", order_id):
        raise StoreError(
            "Store connectivity lost — Bob accidentally unplugged the ethernet"
        )

    # Order successfully received by store — add to KDS
    order_data = config.orders.get(order_id, {})
    await _register_store_order(order_id, {
        "order_id": order_id,
        "items": items if items else order_data.get("items", []),
        "total": order_data.get("total", 0),
        "status": "preparing",
        "created_at": order_data.get("created_at", ""),
    })

    return {
        "accepted": True,
        "order_id": order_id,
        "estimated_ready_minutes": 12,
    }
