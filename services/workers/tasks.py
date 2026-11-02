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
