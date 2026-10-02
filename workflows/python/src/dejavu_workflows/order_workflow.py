from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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

DEFAULT_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class OrderWorkflow:
    """Order processing workflow with saga compensation.

    Orchestrates: validation -> payment hold -> store submission -> pickup signal -> capture.
    If store submission fails permanently, compensates by releasing the payment hold.
    """

    def __init__(self) -> None:
        self._order_ready = False
        self._status = "pending"

    @workflow.signal
    def order_ready(self) -> None:
        """Signal sent from KDS when the store marks the order as ready."""
        self._order_ready = True

    @workflow.query
    def get_status(self) -> str:
        return self._status

    @workflow.run
    async def run(self, order_input: dict) -> dict:
        order_id = order_input["order_id"]
        authorization_id: str | None = None

        # Compensation stack (saga pattern): register compensation *before*
        # executing the step, because the step may succeed but the activity
        # could still fail (timeout, etc.) after the side-effect occurred.
        compensations: list[tuple[str, dict]] = []

        try:
            # Step 1: Validate Order
            self._status = "validating_order"
            await workflow.execute_activity(
                validate_order_activity,
                order_input,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )

            # Step 2: Validate Store
            self._status = "validating_store"
            await workflow.execute_activity(
                validate_store_activity,
                order_input,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=DEFAULT_RETRY,
            )

            # Step 3: Authorize Payment (hold, not capture)
            # Register compensation BEFORE executing — the activity may
            # succeed but the ack could be lost, so we need the compensation
            # on the stack before the side-effect occurs. The compensation
            # must handle the case where the hold was never actually placed.
            self._status = "authorizing_payment"
            compensations.append(("release_payment", {**order_input}))
            payment_result = await workflow.execute_activity(
                authorize_payment_activity,
                order_input,
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=DEFAULT_RETRY,
            )
            authorization_id = payment_result["authorization_id"]
            # Update compensation input with the actual authorization_id
            compensations[-1] = (
                "release_payment",
                {**order_input, "authorization_id": authorization_id},
            )

            # Step 4: Clear Cart
            self._status = "clearing_cart"
            await workflow.execute_activity(
                clear_cart_activity,
                order_input,
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=DEFAULT_RETRY,
            )

            # Step 5: Submit to Store
            # This is the demo failure point — generous retry policy so the
            # presenter can show retries happening in the UI, then "plug in"
            # the store to let the next retry succeed.
            self._status = "submitting_to_store"
            await workflow.execute_activity(
                submit_to_store_activity,
                order_input,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2),
                    backoff_coefficient=1.5,
                    maximum_interval=timedelta(seconds=8),
                    maximum_attempts=10,
                ),
            )

            # Step 6: Wait for order ready signal (human in the loop)
            self._status = "preparing"
            await workflow.wait_condition(lambda: self._order_ready)

            # Step 7: Capture Payment (only after store confirms)
            self._status = "capturing_payment"
            await workflow.execute_activity(
                capture_payment_activity,
                {**order_input, "authorization_id": authorization_id},
                start_to_close_timeout=timedelta(seconds=15),
                retry_policy=DEFAULT_RETRY,
            )

            # Notify customer of success
            self._status = "completed"
            await workflow.execute_activity(
                notify_customer_activity,
                {**order_input, "success": True},
                start_to_close_timeout=timedelta(seconds=10),
            )

            return {"success": True, "order_id": order_id}

        except Exception as e:
            workflow.logger.error(f"Order {order_id} failed: {e}")
            self._status = "compensating"

            # Run compensations in reverse order (saga pattern)
            # asyncio.shield ensures compensations run even if workflow is cancelled
            async def run_compensations():
                for comp_name, comp_input in reversed(compensations):
                    if comp_name == "release_payment":
                        try:
                            await workflow.execute_activity(
                                release_payment_hold_activity,
                                comp_input,
                                start_to_close_timeout=timedelta(seconds=10),
                                retry_policy=RetryPolicy(maximum_attempts=5),
                            )
                        except Exception as comp_err:
                            workflow.logger.error(
                                f"Compensation failed for {comp_name}: {comp_err}"
                            )

            await asyncio.shield(asyncio.ensure_future(run_compensations()))

            # Notify customer of failure
            self._status = "failed"
            await workflow.execute_activity(
                notify_customer_activity,
                {**order_input, "success": False},
                start_to_close_timeout=timedelta(seconds=10),
            )

            return {"success": False, "error": str(e), "order_id": order_id}
