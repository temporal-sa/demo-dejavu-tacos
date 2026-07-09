from __future__ import annotations

import asyncio
import random
import time

from dejavu_tacos.models import FailureScenario, MenuItem, Settings

# ---------------------------------------------------------------------------
# Global mutable state (in-memory, no database)
# ---------------------------------------------------------------------------

settings = Settings()

# Store connectivity — global fallback for callers that don't carry a browser
# session (e.g. cross-language workers). Per-session state below is the source of
# truth for the frontend; set_store_online() mirrors here to keep the two in sync.
store_online: bool = False

# ---------------------------------------------------------------------------
# Per-browser-session store connectivity
# ---------------------------------------------------------------------------
# Each browser tab gets an ephemeral session id (see frontend). Connectivity is
# tracked per session so concurrent users get independent "cable" state.
session_store_online: dict[str, bool] = {}  # session_id -> online?
session_last_seen: dict[str, float] = {}  # session_id -> last-activity epoch secs
order_sessions: dict[str, str] = {}  # order_id -> session_id that placed it

# Fallback cleanup window: sessions idle this long are dropped even if the
# browser never fired its pagehide beacon (crash, mobile background, etc.).
SESSION_TTL_SECONDS = 20 * 60


def _default_online() -> bool:
    """A fresh session starts offline only for the store-connectivity demo,
    so the first order fails and the operator has to plug the cable back in."""
    return settings.failure_scenario != FailureScenario.STORE_CONNECTIVITY


def touch_session(session_id: str | None) -> None:
    """Record activity for a session, initializing its connectivity on first sight."""
    if not session_id:
        return
    if session_id not in session_store_online:
        session_store_online[session_id] = _default_online()
    session_last_seen[session_id] = time.time()


def end_session(session_id: str | None) -> None:
    """Drop all state for a session (fired on tab close / navigate away)."""
    if not session_id:
        return
    session_store_online.pop(session_id, None)
    session_last_seen.pop(session_id, None)
    for order_id in [o for o, s in order_sessions.items() if s == session_id]:
        order_sessions.pop(order_id, None)


def sweep_sessions() -> None:
    """Evict sessions idle past the TTL — fallback for a missed pagehide beacon."""
    now = time.time()
    stale = [s for s, ts in session_last_seen.items() if now - ts > SESSION_TTL_SECONDS]
    for session_id in stale:
        end_session(session_id)


def is_store_online(session_id: str | None) -> bool:
    """Connectivity for a session, falling back to the global flag when the
    caller has no session (cross-language workers, direct API hits)."""
    if session_id and session_id in session_store_online:
        return session_store_online[session_id]
    return store_online


def set_store_online(session_id: str | None, value: bool) -> None:
    """Set connectivity for a session and mirror to the global fallback."""
    global store_online
    if session_id:
        session_store_online[session_id] = value
        session_last_seen[session_id] = time.time()
    store_online = value

# In-memory order storage (customer-side — created when order is placed)
orders: dict[str, dict] = {}

# Store-side orders — only populated when submit_to_store succeeds
# This is what the KDS actually sees
store_orders: dict[str, dict] = {}

# SSE event queues: order_id -> asyncio.Queue
event_queues: dict[str, asyncio.Queue] = {}


def should_fail(step: str, session_id: str | None = None) -> bool:
    """Check whether a step should fail based on the active failure scenario.

    For the store-connectivity scenario the decision is per browser session,
    resolved from the session that placed the order (see order_sessions)."""
    if settings.failure_scenario == FailureScenario.NONE:
        return False
    if settings.failure_scenario == FailureScenario.STORE_CONNECTIVITY:
        return step in ("submit_to_store", "validate_store_submit") and not is_store_online(session_id)
    if settings.failure_scenario == FailureScenario.PAYMENT_ERROR:
        return step == "authorize_payment"
    if settings.failure_scenario == FailureScenario.RANDOM_CHAOS:
        return random.random() < 0.3
    return False


def reset_state() -> None:
    """Reset all in-memory state for a fresh demo run."""
    global store_online
    settings.mode = settings.mode  # keep current mode
    # For store_connectivity scenario, store starts offline so the demo failure triggers
    store_online = settings.failure_scenario != FailureScenario.STORE_CONNECTIVITY
    session_store_online.clear()
    session_last_seen.clear()
    order_sessions.clear()
    orders.clear()
    store_orders.clear()
    # Drain and clear event queues
    for q in event_queues.values():
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
    event_queues.clear()


# ---------------------------------------------------------------------------
# Static menu data
# ---------------------------------------------------------------------------

MENU_ITEMS: list[MenuItem] = [
    MenuItem(
        id="crunch-wrap",
        name="Déjà Vu Crunch Wrap",
        description="A crunchy, cheesy wrap you swear you've had before.",
        price=5.49,
        image="🌯",
        category="Wraps",
    ),
    MenuItem(
        id="taco-supreme",
        name="Temporal Taco Supreme",
        description="Seasoned beef, lettuce, tomato, sour cream — timeless.",
        price=3.99,
        image="🌮",
        category="Tacos",
    ),
    MenuItem(
        id="saga-nachos",
        name="Saga Nachos Bell Grande",
        description="Layers of chips, cheese, beans, and beef. An epic saga in every bite.",
        price=4.79,
        image="🧀",
        category="Sides",
    ),
    MenuItem(
        id="burrito",
        name="Eventual Consistency Burrito",
        description="Everything comes together… eventually.",
        price=6.49,
        image="🌯",
        category="Burritos",
    ),
    MenuItem(
        id="quesadilla",
        name="Idempotent Quesadilla",
        description="Order it twice, get the same delicious result.",
        price=4.99,
        image="🫓",
        category="Specialties",
    ),
    MenuItem(
        id="cinnamon-twists",
        name="Retry Cinnamon Twists",
        description="So good you'll keep coming back.",
        price=1.99,
        image="🍩",
        category="Sweets",
    ),
    MenuItem(
        id="churro",
        name="Compensating Churro",
        description="When things go wrong, this makes it right.",
        price=2.49,
        image="🥖",
        category="Sweets",
    ),
    MenuItem(
        id="baja-blast",
        name="Baja Blast (Durable)",
        description="Refreshingly persistent.",
        price=2.29,
        image="🥤",
        category="Drinks",
    ),
]
