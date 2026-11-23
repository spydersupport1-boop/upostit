"""Celery background worker tasks for asynchronous notification dispatch and lifecycle reconciliation."""

import asyncio
import concurrent.futures
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult

from services.api.database import AsyncSessionLocal, set_tenant_context
from services.api.notifications.dispatcher import NotificationDispatcher
from services.api.notifications.models import DevicePushToken, Notification
from services.api.notifications.schemas import NotificationStatus
from services.workers.celery_app import celery_app

logger = logging.getLogger("attendance.workers.notifications")


def run_async(coro: Any) -> Any:
    """Safely executes an async coroutine from a synchronous Celery worker thread/process."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


@celery_app.task(name="notifications.dispatch_single", bind=True, max_retries=3)
def dispatch_single_notification_task(
    self: Any,
    notification_id_str: str,
    tenant_id_str: str,
) -> dict[str, Any]:
    """Celery background worker task for dispatching a single notification."""
    notification_id = uuid.UUID(notification_id_str)
    tenant_id = uuid.UUID(tenant_id_str)
    logger.info("Executing Celery dispatch task for notification %s, tenant %s", notification_id, tenant_id)

    async def _execute() -> dict[str, Any]:
        if AsyncSessionLocal is None:
            raise RuntimeError("Database connection sessionmaker is unavailable")
        async with AsyncSessionLocal() as session:
            await set_tenant_context(session, str(tenant_id))
            dispatcher = NotificationDispatcher(session)
            result = await dispatcher.dispatch(notification_id, tenant_id)
            await session.commit()
            return result.model_dump(mode="json")

    try:
        result_dict = run_async(_execute())
        if result_dict.get("status") == NotificationStatus.RETRY_SCHEDULED.value:
            # Scheduled for later retry by dispatcher
            logger.info("Notification %s deferred or scheduled for retry", notification_id)
        return cast(dict[str, Any], result_dict)
    except Exception as exc:
        logger.exception("Worker error dispatching notification %s: %s", notification_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="notifications.dispatch_batch", bind=True, max_retries=2)
def dispatch_batch_notifications_task(
    self: Any,
    tenant_id_str: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Celery background task for polling and dispatching due notifications in bounded batches."""
    tenant_id = uuid.UUID(tenant_id_str) if tenant_id_str else None
    logger.info("Executing batch notification dispatch (tenant=%s, limit=%s)", tenant_id, limit)

    async def _execute() -> dict[str, Any]:
        if AsyncSessionLocal is None:
            raise RuntimeError("Database connection sessionmaker is unavailable")
        async with AsyncSessionLocal() as session:
            if tenant_id:
                await set_tenant_context(session, str(tenant_id))
            dispatcher = NotificationDispatcher(session)
            results = await dispatcher.dispatch_pending_batch(tenant_id=tenant_id, limit=limit)
            await session.commit()

            sent_count = sum(1 for r in results if r.status == NotificationStatus.SENT)
            retry_count = sum(1 for r in results if r.status == NotificationStatus.RETRY_SCHEDULED)
            failed_count = sum(1 for r in results if r.status == NotificationStatus.FAILED)

            return {
                "processed": len(results),
                "sent": sent_count,
                "retried": retry_count,
                "failed": failed_count,
            }

    try:
        return cast(dict[str, Any], run_async(_execute()))
    except Exception as exc:
        logger.exception("Batch notification dispatch failed: %s", exc)
        raise self.retry(exc=exc, countdown=15)


@celery_app.task(name="notifications.process_retries")
def process_due_retries_task(limit: int = 50) -> dict[str, Any]:
    """Periodic worker task to process notifications eligible for retry."""
    return cast(dict[str, Any], dispatch_batch_notifications_task(tenant_id_str=None, limit=limit))


@celery_app.task(name="notifications.reconcile_stuck_processing")
def reconcile_stuck_processing_task(timeout_minutes: int = 15) -> dict[str, Any]:
    """Recovers notifications stuck in PROCESSING status due to an unhandled worker crash or termination."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=timeout_minutes)
    logger.info("Reconciling stuck notifications older than %s (cutoff: %s)", timeout_minutes, cutoff)

    async def _reconcile() -> dict[str, Any]:
        if AsyncSessionLocal is None:
            raise RuntimeError("Database connection sessionmaker is unavailable")
        async with AsyncSessionLocal() as session:
            stmt = select(Notification).where(
                Notification.status == NotificationStatus.PROCESSING.value,
                Notification.updated_at <= cutoff,
            )
            stuck_records = (await session.execute(stmt)).scalars().all()

            recovered = 0
            marked_failed = 0

            for notif in stuck_records:
                if notif.attempt_count + 1 < notif.max_attempts:
                    notif.status = NotificationStatus.RETRY_SCHEDULED.value
                    notif.attempt_count += 1
                    notif.scheduled_for = now
                    notif.next_retry_at = now
                    notif.error_message = f"Recovered from stuck PROCESSING status (> {timeout_minutes}m)"
                    notif.updated_at = now
                    recovered += 1
                else:
                    notif.status = NotificationStatus.FAILED.value
                    notif.attempt_count += 1
                    notif.failed_at = now
                    notif.error_message = f"Terminal failure: worker timed out during processing (> {timeout_minutes}m)"
                    notif.updated_at = now
                    marked_failed += 1

            await session.commit()
            return {
                "total_stuck_found": len(stuck_records),
                "recovered_to_retry": recovered,
                "marked_failed": marked_failed,
            }

    return cast(dict[str, Any], run_async(_reconcile()))


@celery_app.task(name="notifications.cleanup_revoked_tokens")
def cleanup_revoked_tokens_task(older_than_days: int = 90) -> dict[str, Any]:
    """Periodic task cleaning up revoked device push tokens beyond the retention window."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=older_than_days)
    logger.info("Purging revoked device tokens older than %s days (cutoff: %s)", older_than_days, cutoff)

    async def _cleanup() -> dict[str, Any]:
        if AsyncSessionLocal is None:
            raise RuntimeError("Database connection sessionmaker is unavailable")
        async with AsyncSessionLocal() as session:
            stmt = delete(DevicePushToken).where(
                DevicePushToken.status.in_(["REVOKED", "EXPIRED"]),
                DevicePushToken.updated_at <= cutoff,
            )
            result = await session.execute(stmt)
            await session.commit()
            cursor_res = cast(CursorResult[Any], result)
            deleted_count = cursor_res.rowcount or 0
            return {"deleted_tokens": deleted_count}

    return cast(dict[str, Any], run_async(_cleanup()))
