#!/usr/bin/env python3
"""
Supabase PostgreSQL & PostGIS Safe Connectivity Verification Script.

Usage:
    python services/api/verify_db.py

Requirements:
- Tests connectivity using safe 'SELECT 1'.
- Checks PostGIS presence using 'SELECT postgis_full_version();'.
- Never prints or logs passwords, credentials, or full connection strings.
- Never resets, drops, or alters any tables or schemas.
- Does not fall back to SQLite or any other database.
- Reports clear error categories and remediation steps if verification fails.
"""

import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.api.config import settings
from services.api.database import check_database_connection, check_postgis_capability


def mask_connection_info(url: str) -> str:
    """Returns a sanitized host description without credentials."""
    if not url:
        return "None"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme.split('+')[0]}://***:***@{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
    except Exception:
        return "[sanitized]"


async def run_verification() -> int:
    print("=" * 70)
    print("Attendance SaaS — Supabase PostgreSQL Connectivity Verification")
    print("=" * 70)

    # 1. Check if DATABASE_URL is supplied
    if not settings.DATABASE_URL:
        print("\n[RESULT] STATUS: NOT VERIFIED")
        print("[ERROR CATEGORY] Missing Configuration: DATABASE_URL is not set.")
        print("\n[REMEDIATION STEPS]")
        print("1. Create an untracked local environment file: .env")
        print("2. Retrieve your database connection string from your Supabase Dashboard:")
        print("   Settings -> Database -> Connection String -> URI (or Session Mode / Transaction Mode Pooler)")
        print("3. Add the following entry to your .env file:")
        print("   DATABASE_URL=postgresql+asyncpg://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres")
        print("4. Re-run this check with: make verify-db or python services/api/verify_db.py")
        print("=" * 70)
        return 1

    sanitized = mask_connection_info(settings.DATABASE_URL)
    print(f"\n[TARGET] Connection Target: {sanitized}")
    print("[INFO] Attempting safe read-only connection test (SELECT 1)...")

    # 2. Test basic connectivity (SELECT 1)
    db_ok, db_msg = await check_database_connection()
    if not db_ok:
        print("\n[RESULT] STATUS: FAILED")
        print(f"[ERROR CATEGORY] Database Connection Failed: {db_msg}")
        print("\n[REMEDIATION STEPS]")
        print("1. Verify your network connection can reach Supabase (port 5432 or 6543 pooler).")
        print("2. Check that the password in DATABASE_URL matches your Supabase database password.")
        print("3. If using Supabase with IPv4 networks, ensure you are connecting through the Supabase connection pooler.")
        print("4. Ensure your project is not in a paused state in the Supabase Dashboard.")
        print("=" * 70)
        return 2

    print("[SUCCESS] Database Connection: OK (safe 'SELECT 1' succeeded)")

    # 3. Test PostGIS capability
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
        return 3

    print(f"[SUCCESS] PostGIS Capability: OK ({gis_msg})")
    print("\n[FINAL VERIFICATION RESULT] Supabase PostgreSQL + PostGIS fully verified!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_verification())
    sys.exit(exit_code)
