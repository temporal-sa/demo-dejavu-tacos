from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from dejavu_tacos import config
from dejavu_tacos.api.events import emit_event, event_generator
from dejavu_tacos.models import (
    ArchitectureMode,
    CreateOrderRequest,
    Order,
    OrderEvent,
    Settings,
    StepStatus,
)
from dejavu_tacos.temporal_client import connect_temporal_client
from dejavu_tacos.temporal_ui import (
    temporal_namespace,
    temporal_namespace_url,
    temporal_ui_base_url,
    temporal_workflow_url,
)
from dejavu_tacos.traditional.handler import process_order_traditional

app = FastAPI(title="Déjà Vu Tacos API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Temporal client (lazy singleton)
# ---------------------------------------------------------------------------

_temporal_client = None


async def get_temporal_client():
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await connect_temporal_client()
    return _temporal_client


# ---------------------------------------------------------------------------
# Health & Menu
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/worker-language")
async def worker_language():
    lang = os.environ.get("DEJAVU_WORKER_LANGUAGE", "python")
    return {"language": lang}


@app.get("/api/temporal-ui")
async def temporal_ui():
    return {
        "base_url": temporal_ui_base_url(),
        "namespace": temporal_namespace(),
        "namespace_url": temporal_namespace_url(),
    }


@app.get("/api/menu")
async def get_menu():
    return [item.model_dump() for item in config.MENU_ITEMS]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.get("/api/settings")
async def get_settings():
    return config.settings.model_dump()


@app.post("/api/settings")
async def update_settings(new_settings: Settings):
    config.settings.mode = new_settings.mode
    config.settings.failure_scenario = new_settings.failure_scenario
    config.settings.presentation_mode = new_settings.presentation_mode
    config.reset_state()
    return config.settings.model_dump()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@app.post("/api/orders")
async def create_order(
    order_request: CreateOrderRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None),
):
    order_id = uuid4().hex[:8]
    total = round(
        sum(item.price * item.quantity for item in order_request.items), 2
    )
    order = Order(order_id=order_id, items=order_request.items, total=total)

    config.orders[order_id] = order.model_dump(mode="json")
    config.event_queues[order_id] = asyncio.Queue()
    # Remember which browser session placed this order so store connectivity is
    # evaluated per-session when submit_to_store runs.
    config.touch_session(x_session_id)
    if x_session_id:
        config.order_sessions[order_id] = x_session_id

    workflow_id = ""
    run_id = ""
    workflow_ui_url = ""

    if config.settings.mode == ArchitectureMode.TRADITIONAL:
        background_tasks.add_task(process_order_traditional, order)
    else:
        # Start Temporal workflow (by string name to avoid importing the workflow package)
        client = await get_temporal_client()
        workflow_id = f"order-{order_id}"
        handle = await client.start_workflow(
            "OrderWorkflow",
            {
                "order_id": order_id,
                "items": [item.model_dump() for item in order_request.items],
                "total": total,
            },
            id=workflow_id,
            task_queue="dejavu-tacos",
        )
        run_id = handle.first_execution_run_id or handle.run_id or ""
        workflow_ui_url = temporal_workflow_url(
            workflow_id=workflow_id,
            run_id=run_id,
        )

    return {
        "order_id": order_id,
        "status": "accepted",
        "total": total,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "temporal_ui_url": workflow_ui_url,
    }


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    order = config.orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/api/orders/{order_id}/events")
async def order_events(order_id: str):
    if order_id not in config.event_queues:
        raise HTTPException(status_code=404, detail="Order not found")
    return EventSourceResponse(event_generator(order_id))


# ---------------------------------------------------------------------------
# Store / KDS
# ---------------------------------------------------------------------------


@app.get("/api/store/status")
async def store_status(x_session_id: str | None = Header(default=None)):
    # The KDS polls this every couple seconds — piggyback the idle-session sweep.
    config.touch_session(x_session_id)
    config.sweep_sessions()
    return {"online": config.is_store_online(x_session_id)}


@app.post("/api/store/toggle-connection")
async def toggle_store_connection(x_session_id: str | None = Header(default=None)):
    new_value = not config.is_store_online(x_session_id)
    config.set_store_online(x_session_id, new_value)
    return {"online": new_value}


@app.post("/api/store/go-online")
async def store_go_online(x_session_id: str | None = Header(default=None)):
    config.set_store_online(x_session_id, True)
    return {"online": True}


@app.post("/api/store/go-offline")
async def store_go_offline(x_session_id: str | None = Header(default=None)):
    config.set_store_online(x_session_id, False)
    return {"online": False}


@app.get("/api/store/orders")
async def get_store_orders(x_session_id: str | None = Header(default=None)):
    """Return orders the store has actually received (via submit_to_store).

    Scoped to the requesting browser session so concurrent demos don't see each
    other's orders; callers without a session (cross-language tooling) see all."""
    if not x_session_id:
        return list(config.store_orders.values())
    return [
        order
        for order_id, order in config.store_orders.items()
        if config.order_sessions.get(order_id) == x_session_id
    ]


@app.post("/api/store/order-ready/{order_id}")
async def mark_order_ready(order_id: str):
    """Signal that an order is ready for pickup (from KDS)."""
    if order_id not in config.store_orders:
        raise HTTPException(status_code=404, detail="Order not received by store")

    # Update store-side status
    config.store_orders[order_id]["status"] = "ready"

    if config.settings.mode == ArchitectureMode.TEMPORAL:
        # Send signal to the Temporal workflow (by string name)
        client = await get_temporal_client()
        handle = client.get_workflow_handle(f"order-{order_id}")
        await handle.signal("order_ready")

    # Emit SSE event
    await emit_event(
        order_id,
        "order_ready",
        StepStatus.COMPLETED,
        mode=config.settings.mode,
        detail="Order marked as ready for pickup!",
    )

    return {"status": "signaled", "order_id": order_id}


@app.post("/api/session/end")
async def end_session(session_id: str = ""):
    """Drop a browser session's state. Called via navigator.sendBeacon on tab
    close / navigate-away, so the id arrives as a query param (beacons can't set
    custom headers). Idle sessions are also swept after SESSION_TTL_SECONDS."""
    config.end_session(session_id)
    return {"status": "ended"}


# ---------------------------------------------------------------------------
# Internal: used by external worker process
# ---------------------------------------------------------------------------


@app.post("/api/internal/events")
async def push_event(event: OrderEvent):
    """Accept SSE events from an external worker process."""
    queue = config.event_queues.get(event.order_id)
    if queue is None:
        if event.order_id in config.orders:
            config.event_queues[event.order_id] = asyncio.Queue()
            queue = config.event_queues[event.order_id]
        else:
            return {"status": "ignored", "reason": "unknown order"}
    await queue.put(event.model_dump(mode="json"))
    return {"status": "accepted"}


@app.get("/api/internal/should-fail/{step}")
async def check_should_fail(step: str, order_id: str = ""):
    """Check if a step should fail based on current failure scenario.

    order_id (when supplied by the worker) resolves the browser session that
    placed the order so connectivity is evaluated per-session."""
    session_id = config.order_sessions.get(order_id) if order_id else None
    return {"should_fail": config.should_fail(step, session_id)}


@app.post("/api/internal/store-orders/{order_id}")
async def register_store_order(order_id: str, payload: dict):
    """Register an order as received by the store (called by submit_to_store activity)."""
    config.store_orders[order_id] = payload
    return {"status": "accepted"}


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


@app.post("/api/reset")
async def reset():
    config.reset_state()
    return {"status": "reset"}
