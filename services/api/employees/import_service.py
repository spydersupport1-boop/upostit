"""Bulk employee import processing engine, validation routines, and S3 report generation."""

import csv
import io
import logging
import re
import uuid
import zipfile
from datetime import UTC, date, datetime
from typing import Any

import openpyxl
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.common.storage import storage_service
from services.api.database import AsyncSessionLocal, set_tenant_context
from services.api.employees.import_schemas import (
    ImportErrorsResponse,
    ImportJobResponse,
    ImportRetryResponse,
    ImportRowError,
)
from services.api.employees.models import Employee, ImportJob
from services.api.locations.models import EmployeeLocation, Location
from services.api.organization.models import Department, Designation

logger = logging.getLogger("attendance.import_service")

# Limits
MAX_IMPORT_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DECOMPRESSED_XLSX_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_IMPORT_ROWS = 2000
CHUNK_SIZE = 100


def sanitize_cell_value(val: Any) -> Any:
    """Neutralizes formula injection prefixes (=, +, @, tabs, returns) in spreadsheet cells."""
    if isinstance(val, str):
        clean = val.strip()
        if clean.startswith(("=", "+", "@", "\t", "\r")):
            return clean.lstrip("=+@\t\r").strip()
        return clean
    return val

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
VALID_EMPLOYMENT_TYPES = {"full_time", "part_time", "contract", "intern", "temporary"}

HEADER_SYNONYMS: dict[str, str] = {
    # employee_id
    "employee_id": "employee_id",
    "employee id": "employee_id",
    "employee_code": "employee_id",
    "employee code": "employee_id",
    "emp_id": "employee_id",
    "empid": "employee_id",
    "code": "employee_id",
    # first_name
    "first_name": "first_name",
    "first name": "first_name",
    "firstname": "first_name",
    "given_name": "first_name",
    # last_name
    "last_name": "last_name",
    "last name": "last_name",
    "lastname": "last_name",
    "surname": "last_name",
    "family_name": "last_name",
    # work_email
    "work_email": "work_email",
    "work email": "work_email",
    "email": "work_email",
    "email_address": "work_email",
    "work_email_address": "work_email",
    # phone_number
    "phone_number": "phone_number",
    "phone number": "phone_number",
    "phone": "phone_number",
    "mobile": "phone_number",
    "contact": "phone_number",
    "contact_number": "phone_number",
    # department
    "department": "department",
    "department_code": "department",
    "department_name": "department",
    "dept": "department",
    "dept_code": "department",
    # designation
    "designation": "designation",
    "designation_code": "designation",
    "designation_title": "designation",
    "title": "designation",
    "role": "designation",
    "position": "designation",
    # reporting_manager
    "reporting_manager": "reporting_manager",
    "reporting manager": "reporting_manager",
    "manager": "reporting_manager",
    "manager_code": "reporting_manager",
    "manager_email": "reporting_manager",
    "reporting_manager_id": "reporting_manager",
    # employment_type
    "employment_type": "employment_type",
    "employment type": "employment_type",
    "type": "employment_type",
    "employmenttype": "employment_type",
    # joining_date
    "joining_date": "joining_date",
    "joining date": "joining_date",
    "date_of_joining": "joining_date",
    "join_date": "joining_date",
    "start_date": "joining_date",
    "hire_date": "joining_date",
    # work_location
    "work_location": "work_location",
    "work location": "work_location",
    "workplace": "work_location",
    "location": "work_location",
    "location_code": "work_location",
    "location_name": "work_location",
}

REQUIRED_CANONICAL_FIELDS = {
    "employee_id",
    "first_name",
    "last_name",
    "work_email",
    "joining_date",
}


def normalize_header(header_name: Any) -> str:
    """Normalizes header string and maps synonyms to canonical field names."""
    if not header_name:
        return ""
    clean = str(header_name).strip().lower()
    clean = re.sub(r"[\s\-_]+", " ", clean)
    return HEADER_SYNONYMS.get(clean, clean.replace(" ", "_"))


def parse_date_value(val: Any) -> date | None:
    """Parses date from various string formats or datetime/date instances."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val

    s = str(val).strip()
    # Try ISO YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    for fmt in (
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y.%m.%d",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_employment_type_value(val: Any) -> str | None:
    """Validates and normalizes employment type string."""
    if not val:
        return "full_time"
    clean = str(val).strip().lower().replace(" ", "_").replace("-", "_")
    if clean in VALID_EMPLOYMENT_TYPES:
        return clean
    return None


def parse_csv_content(data: bytes) -> list[dict[str, Any]]:
    """Decodes and parses CSV byte content into a list of row dicts."""
    text_content = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text_content = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text_content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not decode CSV file. Please ensure it is saved in UTF-8 format.",
        )

    reader = csv.reader(io.StringIO(text_content))
    rows = list(reader)

    # Filter out completely empty lines
    non_empty_rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not non_empty_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file contains no data rows.",
        )

    raw_headers = non_empty_rows[0]
    canonical_headers = [normalize_header(h) for h in raw_headers]

    # Check for duplicate column headers
    seen_headers: set[str] = set()
    duplicate_headers: list[str] = []
    for h in canonical_headers:
        if h in seen_headers:
            duplicate_headers.append(h)
        seen_headers.add(h)
    if duplicate_headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate column header detected in file: {', '.join(sorted(set(duplicate_headers)))}",
        )

    # Validate required canonical headers
    missing = REQUIRED_CANONICAL_FIELDS - set(canonical_headers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns in file header: {', '.join(sorted(missing))}",
        )

    parsed_rows: list[dict[str, Any]] = []
    for row_idx, row_values in enumerate(non_empty_rows[1:], start=2):
        row_dict: dict[str, Any] = {"_row_number": row_idx}
        for col_idx, col_name in enumerate(canonical_headers):
            if col_idx < len(row_values):
                row_dict[col_name] = sanitize_cell_value(row_values[col_idx])
            else:
                row_dict[col_name] = ""
        parsed_rows.append(row_dict)

    return parsed_rows


def parse_xlsx_content(data: bytes) -> list[dict[str, Any]]:
    """Loads and parses XLSX spreadsheet content using openpyxl."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = wb.active
        if sheet is None:
            raise ValueError("No active sheet in Excel workbook")
        raw_rows = list(sheet.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        logger.warning("Failed to parse XLSX workbook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed or unreadable Excel (.xlsx) file.",
        ) from exc

    non_empty_rows = [
        r for r in raw_rows if r and any(cell is not None and str(cell).strip() for cell in r)
    ]
    if not non_empty_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file contains no data rows.",
        )

    raw_headers = non_empty_rows[0]
    canonical_headers = [normalize_header(h) for h in raw_headers]

    # Check for duplicate column headers
    seen_headers = set()
    duplicate_headers = []
    for h in canonical_headers:
        if h in seen_headers:
            duplicate_headers.append(h)
        seen_headers.add(h)
    if duplicate_headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate column header detected in file: {', '.join(sorted(set(duplicate_headers)))}",
        )

    missing = REQUIRED_CANONICAL_FIELDS - set(canonical_headers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns in file header: {', '.join(sorted(missing))}",
        )

    parsed_rows: list[dict[str, Any]] = []
    for row_idx, row_values in enumerate(non_empty_rows[1:], start=2):
        row_dict: dict[str, Any] = {"_row_number": row_idx}
        for col_idx, col_name in enumerate(canonical_headers):
            if col_idx < len(row_values):
                val = row_values[col_idx]
                row_dict[col_name] = sanitize_cell_value(val) if val is not None else ""
            else:
                row_dict[col_name] = ""
        parsed_rows.append(row_dict)

    return parsed_rows


def parse_import_file(data: bytes, filename: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Validates file magic bytes and content, ensuring limits are enforced.
    Returns (file_format, parsed_rows).
    """
    if len(data) > MAX_IMPORT_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed limit of {MAX_IMPORT_FILE_SIZE // (1024 * 1024)} MB.",
        )

    clean_filename = filename.lower()
    is_zip = data.startswith(b"PK\x03\x04")

    if is_zip or clean_filename.endswith(".xlsx"):
        file_format = "xlsx"
        # ZIP bomb inspection: verify decompressed payload does not exceed safety limit
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > MAX_DECOMPRESSED_XLSX_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Decompressed spreadsheet exceeds safety threshold of {MAX_DECOMPRESSED_XLSX_SIZE // (1024 * 1024)} MB.",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed or unreadable XLSX archive.",
            ) from exc
        parsed_rows = parse_xlsx_content(data)
    else:
        file_format = "csv"
        parsed_rows = parse_csv_content(data)

    if len(parsed_rows) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file contains no data rows.",
        )

    if len(parsed_rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed limit of {MAX_IMPORT_ROWS:,} rows (found {len(parsed_rows):,} rows).",
        )

    return file_format, parsed_rows


def generate_import_template_csv() -> str:
    """Generates standard CSV template content with headers and representative sample rows."""
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "employee_id",
        "first_name",
        "last_name",
        "work_email",
        "phone_number",
        "department",
        "designation",
        "reporting_manager",
        "employment_type",
        "joining_date",
        "work_location",
    ]
    writer.writerow(headers)
    sample_row_1 = [
        "EMP-001",
        "Jane",
        "Doe",
        "jane.doe@example.com",
        "+1-555-0101",
        "Engineering",
        "Senior Software Engineer",
        "",
        "full_time",
        "2024-01-15",
        "Headquarters",
    ]
    sample_row_2 = [
        "EMP-002",
        "John",
        "Smith",
        "john.smith@example.com",
        "+1-555-0102",
        "Sales",
        "Account Executive",
        "EMP-001",
        "full_time",
        "2024-02-01",
        "HQ-01",
    ]
    writer.writerow(sample_row_1)
    writer.writerow(sample_row_2)
    return output.getvalue()


async def _load_tenant_reference_caches(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[
    dict[str, uuid.UUID],  # dept_cache (code/name -> id)
    dict[str, uuid.UUID],  # desig_cache (code/title -> id)
    dict[str, uuid.UUID],  # manager_cache (emp_id/email -> id)
    dict[str, uuid.UUID],  # location_cache (code/name -> id)
    set[str],  # existing_emp_ids
    set[str],  # existing_emails
]:
    """Pre-loads tenant lookup dictionaries for high-throughput batch validation."""
    # Departments
    dept_res = await session.execute(
        select(Department).where(Department.tenant_id == tenant_id, Department.is_active.is_(True))
    )
    dept_cache: dict[str, uuid.UUID] = {}
    for d in dept_res.scalars():
        dept_cache[d.code.strip().upper()] = d.id
        dept_cache[d.name.strip().lower()] = d.id
        dept_cache[str(d.id)] = d.id

    # Designations
    desig_res = await session.execute(
        select(Designation).where(
            Designation.tenant_id == tenant_id, Designation.is_active.is_(True)
        )
    )
    desig_cache: dict[str, uuid.UUID] = {}
    for ds in desig_res.scalars():
        desig_cache[ds.code.strip().upper()] = ds.id
        desig_cache[ds.title.strip().lower()] = ds.id
        desig_cache[str(ds.id)] = ds.id

    # Active Employees (for reporting manager lookup) and existing employee duplicates
    emp_res = await session.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
        )
    )
    manager_cache: dict[str, uuid.UUID] = {}
    existing_emp_ids: set[str] = set()
    existing_emails: set[str] = set()

    for e in emp_res.scalars():
        clean_eid = e.employee_id.strip().upper()
        clean_email = e.work_email.strip().lower()
        existing_emp_ids.add(clean_eid)
        existing_emails.add(clean_email)
        if e.status == "active":
            manager_cache[clean_eid] = e.id
            manager_cache[clean_email] = e.id
            manager_cache[str(e.id)] = e.id

    # Locations
    loc_res = await session.execute(
        select(Location).where(Location.tenant_id == tenant_id, Location.is_active.is_(True))
    )
    location_cache: dict[str, uuid.UUID] = {}
    for loc in loc_res.scalars():
        location_cache[loc.code.strip().upper()] = loc.id
        location_cache[loc.name.strip().lower()] = loc.id
        location_cache[str(loc.id)] = loc.id

    return (
        dept_cache,
        desig_cache,
        manager_cache,
        location_cache,
        existing_emp_ids,
        existing_emails,
    )


async def _process_single_chunk(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    chunk: list[dict[str, Any]],
    file_duplicate_errors: dict[int, list[str]],
    dept_cache: dict[str, uuid.UUID],
    desig_cache: dict[str, uuid.UUID],
    manager_cache: dict[str, uuid.UUID],
    location_cache: dict[str, uuid.UUID],
    existing_emp_ids: set[str],
    existing_emails: set[str],
) -> tuple[int, int, list[dict[str, Any]]]:
    """Processes a single batch chunk of rows within the active transaction."""
    chunk_succeeded = 0
    chunk_failed = 0
    chunk_errors: list[dict[str, Any]] = []

    for row in chunk:
        row_num = row["_row_number"]
        errors: list[str] = []

        # Include any whole-file duplicate errors
        if row_num in file_duplicate_errors:
            errors.extend(file_duplicate_errors[row_num])

        # Extract and clean values
        raw_emp_id = str(row.get("employee_id", "")).strip()
        raw_first_name = str(row.get("first_name", "")).strip()
        raw_last_name = str(row.get("last_name", "")).strip()
        raw_email = str(row.get("work_email", "")).strip()
        raw_phone = str(row.get("phone_number", "")).strip() or None
        raw_dept = str(row.get("department", "")).strip()
        raw_desig = str(row.get("designation", "")).strip()
        raw_manager = str(row.get("reporting_manager", "")).strip()
        raw_emp_type = row.get("employment_type", "")
        raw_joining_date = row.get("joining_date", "")
        raw_work_loc = str(row.get("work_location", "")).strip()

        # 1. Required fields
        if not raw_emp_id:
            errors.append("Employee ID is required")
        if not raw_first_name:
            errors.append("First name is required")
        if not raw_last_name:
            errors.append("Last name is required")
        if not raw_email:
            errors.append("Work email is required")
        if not raw_joining_date:
            errors.append("Joining date is required")

        clean_emp_id = raw_emp_id.upper()
        clean_email = raw_email.lower()

        # Field length boundaries
        if len(clean_emp_id) > 50:
            errors.append("Employee ID exceeds maximum length of 50 characters")
        if len(raw_first_name) > 100:
            errors.append("First name exceeds maximum length of 100 characters")
        if len(raw_last_name) > 100:
            errors.append("Last name exceeds maximum length of 100 characters")
        if len(clean_email) > 255:
            errors.append("Work email exceeds maximum length of 255 characters")
        if raw_phone and len(raw_phone) > 50:
            errors.append("Phone number exceeds maximum length of 50 characters")
        if raw_work_loc and len(raw_work_loc) > 100:
            errors.append("Work location exceeds maximum length of 100 characters")

        # 2. Email format validation
        if clean_email and not EMAIL_REGEX.match(clean_email):
            errors.append(f"Invalid email address format: '{raw_email}'")

        # 3. Date format validation
        parsed_joining_date = parse_date_value(raw_joining_date)
        if raw_joining_date and not parsed_joining_date:
            errors.append(
                f"Invalid date format: '{raw_joining_date}'. Expected YYYY-MM-DD or standard date format."
            )

        # 4. Employment type validation
        normalized_emp_type = parse_employment_type_value(raw_emp_type)
        if raw_emp_type and not normalized_emp_type:
            errors.append(
                f"Invalid employment type: '{raw_emp_type}'. Allowed: full_time, part_time, contract, intern, temporary"
            )

        # 5. Database duplicate checks
        if clean_emp_id and clean_emp_id in existing_emp_ids:
            errors.append(
                f"Employee with ID '{clean_emp_id}' already exists in your organization"
            )

        if clean_email and clean_email in existing_emails:
            errors.append(
                f"Employee with work email '{clean_email}' already exists in your organization"
            )

        # 6. Reference resolution: Department
        resolved_dept_id: uuid.UUID | None = None
        if raw_dept:
            clean_d_key_code = raw_dept.upper()
            clean_d_key_name = raw_dept.lower()
            if clean_d_key_code in dept_cache:
                resolved_dept_id = dept_cache[clean_d_key_code]
            elif clean_d_key_name in dept_cache:
                resolved_dept_id = dept_cache[clean_d_key_name]
            elif raw_dept in dept_cache:
                resolved_dept_id = dept_cache[raw_dept]
            else:
                errors.append(
                    f"Department '{raw_dept}' was not found or is inactive in your organization"
                )

        # 7. Reference resolution: Designation
        resolved_desig_id: uuid.UUID | None = None
        if raw_desig:
            clean_ds_key_code = raw_desig.upper()
            clean_ds_key_title = raw_desig.lower()
            if clean_ds_key_code in desig_cache:
                resolved_desig_id = desig_cache[clean_ds_key_code]
            elif clean_ds_key_title in desig_cache:
                resolved_desig_id = desig_cache[clean_ds_key_title]
            elif raw_desig in desig_cache:
                resolved_desig_id = desig_cache[raw_desig]
            else:
                errors.append(
                    f"Designation '{raw_desig}' was not found or is inactive in your organization"
                )

        # 8. Reference resolution: Reporting Manager
        resolved_manager_id: uuid.UUID | None = None
        if raw_manager:
            clean_m_key_code = raw_manager.upper()
            clean_m_key_email = raw_manager.lower()
            if (
                clean_m_key_code == clean_emp_id
                or clean_m_key_email == clean_email
            ):
                errors.append("An employee cannot be their own reporting manager")
            elif clean_m_key_code in manager_cache:
                resolved_manager_id = manager_cache[clean_m_key_code]
            elif clean_m_key_email in manager_cache:
                resolved_manager_id = manager_cache[clean_m_key_email]
            elif raw_manager in manager_cache:
                resolved_manager_id = manager_cache[raw_manager]
            else:
                errors.append(
                    f"Reporting manager '{raw_manager}' was not found or is not an active employee"
                )

        # 9. Reference resolution: Work Location
        resolved_loc_id: uuid.UUID | None = None
        if raw_work_loc:
            clean_l_key_code = raw_work_loc.upper()
            clean_l_key_name = raw_work_loc.lower()
            if clean_l_key_code in location_cache:
                resolved_loc_id = location_cache[clean_l_key_code]
            elif clean_l_key_name in location_cache:
                resolved_loc_id = location_cache[clean_l_key_name]
            elif raw_work_loc in location_cache:
                resolved_loc_id = location_cache[raw_work_loc]
            else:
                errors.append(
                    f"Workplace location '{raw_work_loc}' was not found or is inactive in your organization"
                )

        # Row outcome
        if errors:
            chunk_failed += 1
            err_entry = {
                "row_number": row_num,
                "employee_id": raw_emp_id or None,
                "work_email": raw_email or None,
                "errors": errors,
            }
            chunk_errors.append(err_entry)
        else:
            # Valid row -> Insert Employee
            new_employee = Employee(
                tenant_id=tenant_id,
                employee_id=clean_emp_id,
                first_name=raw_first_name,
                last_name=raw_last_name,
                work_email=clean_email,
                phone_number=raw_phone,
                department_id=resolved_dept_id,
                designation_id=resolved_desig_id,
                reporting_manager_id=resolved_manager_id,
                employment_type=normalized_emp_type or "full_time",
                joining_date=parsed_joining_date or date.today(),
                status="active",
                work_location=raw_work_loc or None,
            )
            session.add(new_employee)
            await session.flush()

            # If workplace location was resolved, create primary workplace assignment
            if resolved_loc_id:
                assignment = EmployeeLocation(
                    tenant_id=tenant_id,
                    employee_id=new_employee.id,
                    location_id=resolved_loc_id,
                    is_primary=True,
                    effective_from=new_employee.joining_date,
                    effective_to=None,
                )
                session.add(assignment)

            # Update in-memory duplicate tracker to prevent collisions within subsequent chunks
            existing_emp_ids.add(clean_emp_id)
            existing_emails.add(clean_email)
            # Add newly created employee to manager lookup cache so subsequent rows can reference them!
            manager_cache[clean_emp_id] = new_employee.id
            manager_cache[clean_email] = new_employee.id
            manager_cache[str(new_employee.id)] = new_employee.id

            chunk_succeeded += 1

    await session.flush()
    return chunk_succeeded, chunk_failed, chunk_errors


async def process_import_job_chunks(job_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
    """
    Executes asynchronous chunk processing (100 rows per chunk) for an import job.
    Supports checkpoint resumption and retry idempotency.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("Database session factory unavailable")

    async with AsyncSessionLocal() as session:
        # Enforce PostgreSQL tenant context and RLS
        await set_tenant_context(session, str(tenant_id))

        job_query = await session.execute(
            select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id).with_for_update()
        )
        job = job_query.scalar_one_or_none()
        if not job:
            logger.error("Import job %s not found for tenant %s", job_id, tenant_id)
            return {"status": "not_found", "job_id": str(job_id)}

        if job.status == "completed":
            logger.info("Import job %s is already completed. Skipping.", job_id)
            return {"status": "completed", "job_id": str(job_id)}

        if job.status == "processing":
            logger.warning("Import job %s is already being processed by another worker. Skipping.", job_id)
            return {"status": "already_processing", "job_id": str(job_id)}

        # Mark job as processing
        job.status = "processing"
        if not job.started_at:
            job.started_at = datetime.now(UTC)
        await session.commit()

        # Verify tenant isolation on storage key
        expected_prefix = f"tenants/{tenant_id}/"
        if not job.s3_file_key.startswith(expected_prefix):
            logger.error("Security alert: job %s has foreign s3_file_key: %s", job_id, job.s3_file_key)
            job.status = "failed"
            job.error_summary = [
                {"row_number": 0, "errors": ["Tenant storage path isolation violation"]}
            ]
            await session.commit()
            return {"status": "failed", "job_id": str(job_id)}

        # Download raw file bytes from storage
        try:
            file_bytes = storage_service.download_file(job.s3_file_key)
        except Exception as exc:
            logger.exception("Failed to download file for job %s: %s", job_id, exc)
            job.status = "failed"
            job.error_summary = [
                {"row_number": 0, "errors": [f"Storage file download error: {exc!s}"]}
            ]
            await session.commit()
            return {"status": "failed", "job_id": str(job_id)}

        # Parse file rows
        try:
            _, parsed_rows = parse_import_file(file_bytes, job.file_name)
        except HTTPException as exc:
            job.status = "failed"
            job.error_summary = [{"row_number": 0, "errors": [exc.detail]}]
            await session.commit()
            return {"status": "failed", "job_id": str(job_id)}
        except Exception as exc:
            logger.exception("Failed parsing rows for job %s: %s", job_id, exc)
            job.status = "failed"
            job.error_summary = [{"row_number": 0, "errors": [f"Parsing error: {exc!s}"]}]
            await session.commit()
            return {"status": "failed", "job_id": str(job_id)}

        total_rows = len(parsed_rows)
        job.total_rows = total_rows

        # Pre-scan for in-file duplicates across entire file
        seen_file_emp_ids: dict[str, int] = {}
        seen_file_emails: dict[str, int] = {}
        file_duplicate_errors: dict[int, list[str]] = {}

        for r in parsed_rows:
            r_num = r["_row_number"]
            e_id = str(r.get("employee_id", "")).strip().upper()
            w_email = str(r.get("work_email", "")).strip().lower()

            if e_id:
                if e_id in seen_file_emp_ids:
                    first_row = seen_file_emp_ids[e_id]
                    file_duplicate_errors.setdefault(r_num, []).append(
                        f"Duplicate employee ID '{e_id}' within the import file (first seen at row {first_row})"
                    )
                else:
                    seen_file_emp_ids[e_id] = r_num

            if w_email:
                if w_email in seen_file_emails:
                    first_row = seen_file_emails[w_email]
                    file_duplicate_errors.setdefault(r_num, []).append(
                        f"Duplicate work email '{w_email}' within the import file (first seen at row {first_row})"
                    )
                else:
                    seen_file_emails[w_email] = r_num

        # Pre-load tenant caches
        (
            dept_cache,
            desig_cache,
            manager_cache,
            location_cache,
            existing_emp_ids,
            existing_emails,
        ) = await _load_tenant_reference_caches(session, tenant_id)

        # Resume from checkpoint
        current_idx = job.last_processed_row_index or 0
        job.last_processed_row_index = current_idx
        job.succeeded_rows = job.succeeded_rows or 0
        job.failed_rows = job.failed_rows or 0
        job.processed_rows = job.processed_rows or 0
        all_row_errors: list[dict[str, Any]] = list(job.error_summary or [])

        # Process in chunks of CHUNK_SIZE
        while current_idx < total_rows:
            chunk = parsed_rows[current_idx : current_idx + CHUNK_SIZE]
            try:
                chunk_succeeded, chunk_failed, chunk_errors = await _process_single_chunk(
                    session=session,
                    tenant_id=tenant_id,
                    chunk=chunk,
                    file_duplicate_errors=file_duplicate_errors,
                    dept_cache=dept_cache,
                    desig_cache=desig_cache,
                    manager_cache=manager_cache,
                    location_cache=location_cache,
                    existing_emp_ids=existing_emp_ids,
                    existing_emails=existing_emails,
                )

                # Commit chunk and advance bookmark
                current_idx += len(chunk)
                job.last_processed_row_index = current_idx
                job.processed_rows = current_idx
                job.succeeded_rows += chunk_succeeded
                job.failed_rows += chunk_failed
                all_row_errors.extend(chunk_errors)
                job.error_summary = all_row_errors[:1000]  # Store up to 1000 in JSONB
                await session.commit()
                logger.info(
                    "Import job %s: processed chunk up to row %d/%d (succeeded: %d, failed: %d)",
                    job_id,
                    current_idx,
                    total_rows,
                    job.succeeded_rows,
                    job.failed_rows,
                )
            except Exception as exc:
                logger.exception(
                    "Import job %s: chunk starting at index %d failed unexpectedly: %s",
                    job_id,
                    current_idx,
                    exc,
                )
                await session.rollback()
                job_ref = await session.execute(
                    select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id)
                )
                failed_job = job_ref.scalar_one_or_none()
                if failed_job:
                    failed_job.status = "failed"
                    errs = list(failed_job.error_summary or [])
                    errs.append({
                        "row_number": current_idx + 1,
                        "errors": [f"Database transaction failure during chunk processing: {exc!s}"],
                    })
                    failed_job.error_summary = errs[:1000]
                    await session.commit()
                return {
                    "status": "failed",
                    "job_id": str(job_id),
                    "last_processed_row_index": current_idx,
                    "error": str(exc),
                }

        # All chunks completed
        job.status = "completed"
        job.completed_at = datetime.now(UTC)

        # Generate and upload error report CSV if there were failures
        if job.failed_rows > 0:
            try:
                error_csv_str = _generate_failure_csv_report(all_row_errors)
                error_s3_key = storage_service.get_tenant_error_report_path(tenant_id, job_id)
                storage_service.upload_file(
                    error_s3_key,
                    error_csv_str.encode("utf-8"),
                    content_type="text/csv",
                )
                job.s3_error_key = error_s3_key
            except Exception as exc:
                logger.warning("Failed uploading error report to S3 for job %s: %s", job_id, exc)

        await session.commit()
        logger.info(
            "Import job %s finished. Total: %d, Succeeded: %d, Failed: %d",
            job_id,
            job.total_rows,
            job.succeeded_rows,
            job.failed_rows,
        )

        return {
            "status": job.status,
            "job_id": str(job_id),
            "total_rows": job.total_rows,
            "succeeded_rows": job.succeeded_rows,
            "failed_rows": job.failed_rows,
        }


def _generate_failure_csv_report(row_errors: list[dict[str, Any]]) -> str:
    """Serializes row errors into a downloadable CSV failure report."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Row Number", "Employee ID", "Work Email", "Errors"])
    for item in row_errors:
        writer.writerow(
            [
                item.get("row_number", ""),
                item.get("employee_id", ""),
                item.get("work_email", ""),
                " | ".join(item.get("errors", [])),
            ]
        )
    return output.getvalue()


def to_import_job_response(job: ImportJob) -> ImportJobResponse:
    """Converts ImportJob ORM model to API response schema."""
    processed = job.processed_rows or 0
    total = job.total_rows or 0
    pct = 0.0
    if total > 0:
        pct = round(min(100.0, (processed / total) * 100.0), 1)

    now = datetime.now(UTC)
    return ImportJobResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        created_by_user_id=job.created_by_user_id,
        file_name=job.file_name,
        file_format=job.file_format,
        status=job.status,
        total_rows=total,
        processed_rows=processed,
        succeeded_rows=job.succeeded_rows or 0,
        failed_rows=job.failed_rows or 0,
        progress_percentage=pct,
        last_processed_row_index=job.last_processed_row_index or 0,
        has_error_report=bool(job.s3_error_key),
        error_summary=job.error_summary or [],
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at or now,
        updated_at=job.updated_at or now,
    )


async def get_import_job(
    session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> ImportJobResponse:
    """Fetches import job status ensuring tenant isolation."""
    query = await session.execute(
        select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id)
    )
    job = query.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found in your organization",
        )
    return to_import_job_response(job)


async def get_import_job_errors(
    session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> ImportErrorsResponse:
    """Fetches line-by-line error diagnostics for an import job."""
    query = await session.execute(
        select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id)
    )
    job = query.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found in your organization",
        )

    parsed_errors = [
        ImportRowError(
            row_number=err.get("row_number", 0),
            employee_id=err.get("employee_id"),
            work_email=err.get("work_email"),
            errors=err.get("errors", []),
        )
        for err in (job.error_summary or [])
    ]

    download_url = (
        f"/api/v1/employees/import/{job_id}/errors/download" if job.s3_error_key else None
    )

    return ImportErrorsResponse(
        job_id=job.id,
        status=job.status,
        total_failed_rows=job.failed_rows,
        errors=parsed_errors,
        download_url=download_url,
    )


async def download_import_job_error_report(
    session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> bytes:
    """Downloads the generated CSV failure report from object storage."""
    query = await session.execute(
        select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id)
    )
    job = query.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found in your organization",
        )
    if not job.s3_error_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No error report exists for this import job",
        )

    # Verify tenant storage key isolation
    expected_prefix = f"tenants/{tenant_id}/"
    if not job.s3_error_key.startswith(expected_prefix):
        logger.error(
            "Security violation: import job %s has foreign s3_error_key %s",
            job_id,
            job.s3_error_key,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to storage object outside your tenant",
        )

    try:
        return storage_service.download_file(job.s3_error_key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve error report from storage",
        ) from exc


async def retry_import_job(
    session: AsyncSession, tenant_id: uuid.UUID, job_id: uuid.UUID
) -> ImportRetryResponse:
    """
    Safely retries an interrupted or failed import job from its last checkpoint.
    Acquires row-level lock to prevent concurrent worker or retry execution.
    """
    query = await session.execute(
        select(ImportJob)
        .where(ImportJob.id == job_id, ImportJob.tenant_id == tenant_id)
        .with_for_update()
    )
    job = query.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found in your organization",
        )

    if job.status == "processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Import job is currently being processed by an active worker.",
        )

    if job.status == "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Import job is already queued for processing.",
        )

    if job.status == "completed" and (job.processed_rows or 0) >= (job.total_rows or 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import job has already finished processing all rows.",
        )

    resumed_from = job.last_processed_row_index or 0
    job.status = "queued"
    await session.commit()

    return ImportRetryResponse(
        job_id=job.id,
        status=job.status,
        resumed_from_row_index=resumed_from,
        message=f"Import job retry scheduled from row {resumed_from + 1}.",
    )
