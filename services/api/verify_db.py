#!/usr/bin/env python3
"""
Supabase PostgreSQL & PostGIS Safe Connectivity Verification Script.

Usage:
    python services/api/verify_db.py

Requirements:
- Tests Supabase API & Project connectivity.
- Tests direct PostgreSQL connectivity using safe 'SELECT 1'.
- Checks PostGIS presence using 'SELECT postgis_full_version();'.
- Never prints or logs passwords, credentials, or full connection strings.
- Never resets, drops, or alters any tables or schemas.
- Does not fall back to SQLite or any other database.
- Reports clear error categories and remediation steps if verification fails.
"""

import asyncio
import os
import sys
from urllib.parse import urlparse

import httpx

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.api.config import settings
from services.api.database import check_database_connection, check_postgis_capability


def mask_connection_info(url: str) -> str:
    """Returns a sanitized host description without credentials."""
    if not url:
        return "None"
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme.split('+')[0]}://***:***@{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
    except Exception:
        return "[sanitized]"


async def verify_supabase_api() -> tuple[bool, str]:
    """Verify Supabase Project API endpoint using service role key."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        return False, "SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not configured"

    target_url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(target_url, headers=headers)
            if resp.status_code == 200:
                project_ref = resp.headers.get("sb-project-ref", "active")
                return True, f"project '{project_ref}' active and reachable (HTTP 200 OK)"
            return False, f"Supabase API returned HTTP {resp.status_code}"
    except Exception as e:
        return False, f"could not reach Supabase endpoint ({type(e).__name__})"


async def run_verification() -> int:
    print("=" * 70)
    print("Attendance SaaS — Supabase Project & Database Verification")
    print("=" * 70)

    # 1. Verify Supabase Project REST API connectivity
    print("\n[STEP 1] Probing Supabase Project API Endpoint...")
    if settings.SUPABASE_URL:
        print(f"[TARGET] Supabase URL: {settings.SUPABASE_URL}")
        api_ok, api_msg = await verify_supabase_api()
        if api_ok:
            print(f"[SUCCESS] Supabase Project: OK ({api_msg})")
        else:
            print(f"[WARNING] Supabase Project API Probe: {api_msg}")
    else:
        print("[INFO] SUPABASE_URL not configured. Skipping API probe.")

    # 2. Check DATABASE_URL configuration
    print("\n[STEP 2] Verifying Direct PostgreSQL & PostGIS Connection...")
    if not settings.DATABASE_URL:
        print("\n[RESULT] DIRECT POSTGRES STATUS: NOT CONFIGURED")
        print("[ERROR CATEGORY] Missing Configuration: DATABASE_URL is not set.")
        print("\n[REMEDIATION STEPS]")
        print("1. Set DATABASE_URL in your untracked .env file.")
        print("=" * 70)
        return 1

    if "[YOUR-PASSWORD]" in settings.DATABASE_URL:
        sanitized = mask_connection_info(settings.DATABASE_URL)
        print(f"[TARGET] Connection Target: {sanitized}")
        print("\n[RESULT] DIRECT POSTGRES STATUS: AWAITING DATABASE PASSWORD")
        print(
            "[ERROR CATEGORY] Missing Password: '[YOUR-PASSWORD]' placeholder detected in DATABASE_URL."
        )
        print("\n[REMEDIATION STEPS TO CONNECT TO SUPABASE POSTGRESQL DIRECTLY]")
        print(
            f"1. In your Supabase Dashboard for project '{settings.SUPABASE_PROJECT_REF or 'qnkgndfzuhrjuopzlcxy'}':"
        )
        print("   Navigate to: Project Settings -> Database")
        print("2. If you know your database password:")
        print("   Edit .env and replace [YOUR-PASSWORD] with your actual password.")
        print("3. If you forgot or did not set a custom password:")
        print("   Click 'Reset Database Password' in Supabase Project Settings -> Database.")
        print("4. Connection String format:")
        print(
            f"   DATABASE_URL=postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.{settings.SUPABASE_PROJECT_REF or 'qnkgndfzuhrjuopzlcxy'}.supabase.co:5432/postgres"
        )
        print("   (Or use the Connection Pooler URI on port 6543 if connecting via IPv4).")
        print("5. Re-run: make verify-db")
        print("=" * 70)
        return 2

    sanitized = mask_connection_info(settings.DATABASE_URL)
    print(f"[TARGET] Connection Target: {sanitized}")
    print("[INFO] Attempting safe read-only connection test (SELECT 1)...")

    # 3. Test basic PostgreSQL connectivity (SELECT 1)
    db_ok, db_msg = await check_database_connection()
    if not db_ok:
        print("\n[RESULT] STATUS: FAILED")
        print(f"[ERROR CATEGORY] Database Connection Failed: {db_msg}")
        print("\n[REMEDIATION STEPS]")
        print("1. Verify your network connection can reach Supabase (port 5432 or 6543 pooler).")
        print("2. Check that the password in DATABASE_URL matches your Supabase database password.")
        print(
            "3. If using Supabase with IPv4 networks, ensure you are connecting through the Supabase connection pooler."
        )
        print("4. Ensure your project is not in a paused state in the Supabase Dashboard.")
        print("=" * 70)
        return 3

    print("[SUCCESS] Direct Database Connection: OK (safe 'SELECT 1' succeeded)")

    # 4. Test PostGIS capability
    print("[INFO] Checking PostGIS extension capability (SELECT postgis_full_version())...")
    gis_ok, gis_msg = await check_postgis_capability()
    if not gis_ok:
        print(f"[WARNING] PostGIS Status: {gis_msg}")
        print("\n[REMEDIATION STEPS TO ENABLE POSTGIS IN SUPABASE]")
        print("1. Go to your Supabase Project Dashboard.")
        print("2. Navigate to Database -> Extensions.")
        print("3. Search for 'postgis' and toggle 'Enable Extension'.")
        print("   Or run SQL: CREATE EXTENSION IF NOT EXISTS postgis;")
        print("=" * 70)
        return 4

    print(f"[SUCCESS] PostGIS Capability: OK ({gis_msg})")
    print("\n[FINAL VERIFICATION RESULT] Supabase PostgreSQL + PostGIS fully verified!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_verification())
    sys.exit(exit_code)
