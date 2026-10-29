#!/usr/bin/env python3
"""Celery worker configuration smoke test."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.workers.celery_app import celery_app, ping_task


def run_smoke_test() -> int:
    print("=" * 60)
    print("Attendance SaaS — Celery Worker Smoke Test")
    print("=" * 60)

    # 1. Verify app configuration
    print(f"[INFO] Celery App Name: {celery_app.main}")
    print(f"[INFO] Task Serializer: {celery_app.conf.task_serializer}")
    print(f"[INFO] Timezone: {celery_app.conf.timezone}")

    # 2. Verify registered tasks
    registered = [name for name in celery_app.tasks.keys() if not name.startswith("celery.")]
    print(f"[INFO] Registered Domain Tasks: {registered}")

    if "attendance.ping" not in celery_app.tasks:
        print("[FAIL] 'attendance.ping' task is not registered in Celery app!")
        return 1

    # 3. Direct task execution test
    result = ping_task()
    if result != "pong":
        print(f"[FAIL] Expected 'pong', got {result}")
        return 1

    print("[SUCCESS] ping_task executed directly and returned 'pong'")
    print("[SUCCESS] Celery worker configuration verified successfully!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_smoke_test())
