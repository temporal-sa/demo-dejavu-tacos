from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from dejavu_tacos.temporal_client import connect_temporal_client
from dejavu_workflows.activities import (
    authorize_payment_activity,
    capture_payment_activity,
    clear_cart_activity,
    notify_customer_activity,
    release_payment_hold_activity,
    submit_to_store_activity,
    validate_order_activity,
    validate_store_activity,
)
from dejavu_workflows.order_workflow import TASK_QUEUE, OrderWorkflow


async def run_worker(client: Client | None = None) -> None:
    """Start the Temporal worker. Accepts an optional pre-connected client."""
    if client is None:
        client = await connect_temporal_client()

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[OrderWorkflow],
        activities=[
            validate_order_activity,
            validate_store_activity,
            authorize_payment_activity,
            clear_cart_activity,
            submit_to_store_activity,
            capture_payment_activity,
            release_payment_hold_activity,
            notify_customer_activity,
        ],
    )
    print(f"Worker started ok, listening on task queue: {TASK_QUEUE}")
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
