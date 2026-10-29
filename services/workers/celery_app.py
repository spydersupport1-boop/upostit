"""Celery application configuration for asynchronous background workloads."""

from celery import Celery

from services.api.config import settings

celery_app = Celery(
    "attendance_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="attendance.ping")
def ping_task() -> str:
    """Smoke test task to verify Celery worker registration."""
    return "pong"
