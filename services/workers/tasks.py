"""Celery tasks for background asynchronous workloads."""

import asyncio
import concurrent.futures
import logging
import uuid
from typing import Any

from services.workers.celery_app import celery_app

logger = logging.getLogger("attendance.workers.tasks")


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


@celery_app.task(name="attendance.process_bulk_employee_import", bind=True, max_retries=3)
def process_bulk_employee_import_task(
    self: Any, job_id_str: str, tenant_id_str: str
) -> dict[str, Any]:
    """Celery background worker task for processing bulk employee imports in chunks."""
    from services.api.employees.import_service import process_import_job_chunks

    job_id = uuid.UUID(job_id_str)
    tenant_id = uuid.UUID(tenant_id_str)
    logger.info("Executing Celery import task for job: %s, tenant: %s", job_id, tenant_id)

    try:
        from typing import cast

        result = run_async(process_import_job_chunks(job_id, tenant_id))
        return cast(dict[str, Any], result)
    except Exception as exc:
        logger.exception("Bulk employee import failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="attendance.nightly_reconciliation", bind=True, max_retries=3)
def reconcile_nightly_attendance_task(
    self: Any,
    tenant_id_str: str,
    target_date_str: str | None = None,
    employee_id_str: str | None = None,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Celery background task for reconciling daily attendance projections."""
    from datetime import date

    from services.api.attendance.reconciliation import run_attendance_reconciliation
    from services.api.attendance.schemas import ReconciliationRequest
    from services.api.database import AsyncSessionLocal

    tenant_id = uuid.UUID(tenant_id_str)
    t_date = date.fromisoformat(target_date_str) if target_date_str else None
    emp_id = uuid.UUID(employee_id_str) if employee_id_str else None

    logger.info(
        "Executing attendance reconciliation task for tenant: %s, date: %s", tenant_id, t_date
    )

    async def _execute() -> dict[str, Any]:
        if AsyncSessionLocal is None:
            raise RuntimeError("Database session factory is not configured.")
        async with AsyncSessionLocal() as session:
            payload = ReconciliationRequest(
                target_date=t_date,
                employee_id=emp_id,
                batch_size=batch_size,
            )
            result = await run_attendance_reconciliation(session, tenant_id, payload)
            await session.commit()
            return result.model_dump(mode="json")

    try:
        from typing import cast

        res = run_async(_execute())
        return cast(dict[str, Any], res)
    except Exception as exc:
        logger.exception("Attendance reconciliation failed for tenant %s: %s", tenant_id, exc)
        raise self.retry(exc=exc, countdown=60)
