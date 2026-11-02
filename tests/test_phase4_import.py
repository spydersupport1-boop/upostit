"""Unit and API integration tests for Phase 4 Milestone 3 Bulk Employee Import."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import openpyxl
import pytest
from httpx import ASGITransport, AsyncClient

from services.api.auth.dependencies import AuthenticatedContext, get_authenticated_context
from services.api.auth.models import User
from services.api.common.storage import storage_service
from services.api.database import get_db
from services.api.employees.import_service import (
    MAX_IMPORT_FILE_SIZE,
    MAX_IMPORT_ROWS,
    generate_import_template_csv,
    parse_date_value,
    parse_employment_type_value,
    parse_import_file,
    process_import_job_chunks,
)
from services.api.employees.models import Employee, ImportJob
from services.api.locations.models import Location
from services.api.main import app
from services.api.organization.models import Department, Designation
from services.api.tenants.models import Tenant
from services.workers.tasks import process_bulk_employee_import_task


def _mock_context(
    role: str, tenant_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None
) -> AuthenticatedContext:
    tid = tenant_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user = User(
        id=uid,
        tenant_id=tid,
        email=f"test_{role}@corp.test",
        password_hash="argon2id$mock",
        role=role,
        status="active",
    )
    tenant = Tenant(
        id=tid,
        name="Test Import Corp",
        slug=f"test-import-{tid.hex[:6]}",
        company_email="admin@import.test",
        country_code="US",
        status="active",
    )
    return AuthenticatedContext(user=user, tenant=tenant)


def _generate_valid_csv(num_rows: int = 5) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
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
    ])
    for i in range(1, num_rows + 1):
        writer.writerow([
            f"EMP-{i:04d}",
            f"First{i}",
            f"Last{i}",
            f"user{i}@example.com",
            f"+1-555-010{i}",
            "Engineering",
            "Software Engineer",
            "",
            "full_time",
            "2024-01-15",
            "Headquarters",
        ])
    return output.getvalue().encode("utf-8")


def _generate_valid_xlsx(num_rows: int = 3) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees"
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
    ws.append(headers)
    for i in range(1, num_rows + 1):
        ws.append([
            f"XLS-{i:04d}",
            f"ExcelFirst{i}",
            f"ExcelLast{i}",
            f"excel{i}@example.com",
            f"+1-555-020{i}",
            "Sales",
            "Account Executive",
            "",
            "full_time",
            "2024-02-01",
            "HQ",
        ])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ===========================================================================
# 1. Parsing and Validation Unit Tests
# ===========================================================================


def test_date_parsing_variations():
    """Verify robust date parsing across formats."""
    assert parse_date_value("2024-03-25") == date(2024, 3, 25)
    assert parse_date_value("25-03-2024") == date(2024, 3, 25)
    assert parse_date_value("25/03/2024") == date(2024, 3, 25)
    assert parse_date_value(date(2024, 1, 1)) == date(2024, 1, 1)
    assert parse_date_value(datetime(2024, 1, 1, 12, 0, tzinfo=UTC)) == date(2024, 1, 1)
    assert parse_date_value("invalid-date") is None
    assert parse_date_value("") is None


def test_employment_type_normalization():
    """Verify employment type normalization and enum validation."""
    assert parse_employment_type_value("full_time") == "full_time"
    assert parse_employment_type_value("Full Time") == "full_time"
    assert parse_employment_type_value("Part-Time") == "part_time"
    assert parse_employment_type_value("contract") == "contract"
    assert parse_employment_type_value("INTERN") == "intern"
    assert parse_employment_type_value("temporary") == "temporary"
    assert parse_employment_type_value("") == "full_time"
    assert parse_employment_type_value("ceo") is None


def test_template_generation():
    """Verify template CSV generates valid headers and sample rows."""
    template_str = generate_import_template_csv()
    assert "employee_id,first_name,last_name,work_email" in template_str
    assert "EMP-001" in template_str


def test_file_parser_csv_success():
    """Verify CSV parser correctly extracts canonical fields."""
    data = _generate_valid_csv(num_rows=2)
    fmt, rows = parse_import_file(data, "test.csv")
    assert fmt == "csv"
    assert len(rows) == 2
    assert rows[0]["employee_id"] == "EMP-0001"
    assert rows[0]["_row_number"] == 2


def test_file_parser_xlsx_success():
    """Verify XLSX parser correctly extracts rows and header mappings."""
    data = _generate_valid_xlsx(num_rows=3)
    fmt, rows = parse_import_file(data, "test.xlsx")
    assert fmt == "xlsx"
    assert len(rows) == 3
    assert rows[0]["employee_id"] == "XLS-0001"


def test_file_parser_exceeds_row_limit():
    """Verify files with > 2,000 rows are rejected."""
    data = _generate_valid_csv(num_rows=MAX_IMPORT_ROWS + 5)
    with pytest.raises(Exception) as exc:
        parse_import_file(data, "bulk.csv")
    assert "2,000" in str(exc.value)


def test_file_parser_exceeds_file_size():
    """Verify oversized byte payloads (> 10MB) are rejected."""
    oversized = b"a" * (MAX_IMPORT_FILE_SIZE + 1024)
    with pytest.raises(Exception) as exc:
        parse_import_file(oversized, "huge.csv")
    assert "10 MB" in str(exc.value)


def test_file_parser_missing_required_headers():
    """Verify CSV missing required headers is rejected with 400."""
    csv_missing = b"first_name,last_name\nJane,Doe\n"
    with pytest.raises(Exception) as exc:
        parse_import_file(csv_missing, "bad.csv")
    assert "Missing required columns" in str(exc.value)


# ===========================================================================
# 2. Storage Service Unit Tests (Mocked S3 / In-Memory Fallback)
# ===========================================================================


def test_storage_service_tenant_paths():
    """Verify tenant isolation in S3 key derivation."""
    tid = uuid.uuid4()
    jid = uuid.uuid4()
    path = storage_service.get_tenant_import_path(tid, jid, "staff.csv")
    assert path == f"tenants/{tid}/imports/{jid}/staff.csv"

    err_path = storage_service.get_tenant_error_report_path(tid, jid)
    assert err_path == f"tenants/{tid}/imports/{jid}/errors.csv"


def test_storage_service_upload_and_download():
    """Verify upload and download using storage service (in-memory test fallback)."""
    key = f"test/file_{uuid.uuid4()}.txt"
    content = b"test employee data"
    uploaded_key = storage_service.upload_file(key, content, content_type="text/plain")
    assert uploaded_key == key

    downloaded = storage_service.download_file(key)
    assert downloaded == content

    storage_service.delete_file(key)


# ===========================================================================
# 3. RBAC and Auth Endpoint Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_import_endpoints_require_authentication():
    """Verify all /import endpoints return 401 when unauthenticated."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.get("/api/v1/employees/import/template")
        assert res1.status_code == 401

        res2 = await client.post("/api/v1/employees/import")
        assert res2.status_code == 401

        res3 = await client.get(f"/api/v1/employees/import/{uuid.uuid4()}")
        assert res3.status_code == 401

        res4 = await client.get(f"/api/v1/employees/import/{uuid.uuid4()}/errors")
        assert res4.status_code == 401

        res5 = await client.post(f"/api/v1/employees/import/{uuid.uuid4()}/retry")
        assert res5.status_code == 401


@pytest.mark.asyncio
async def test_manager_and_employee_roles_forbidden_from_import():
    """Verify MANAGER and EMPLOYEE roles receive 403 Forbidden on import endpoints."""
    for role in ("manager", "employee"):
        auth_ctx = _mock_context(role)
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res_template = await client.get("/api/v1/employees/import/template")
            assert res_template.status_code == 403

            files = {"file": ("test.csv", b"dummy", "text/csv")}
            res_upload = await client.post("/api/v1/employees/import", files=files)
            assert res_upload.status_code == 403

            res_retry = await client.post(f"/api/v1/employees/import/{uuid.uuid4()}/retry")
            assert res_retry.status_code == 403

        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_template_download_allowed_for_hr_admin_owner():
    """Verify OWNER, ADMIN, and HR can download the import CSV template."""
    for role in ("owner", "admin", "hr"):
        auth_ctx = _mock_context(role)
        app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/employees/import/template")
            assert res.status_code == 200
            assert res.headers["content-type"].startswith("text/csv")
            assert "employee_id,first_name,last_name" in res.text

        app.dependency_overrides.clear()


# ===========================================================================
# 4. Upload API Tests (CSV and XLSX)
# ===========================================================================


@pytest.mark.asyncio
async def test_upload_csv_creates_import_job_and_returns_202():
    """Verify uploading a valid CSV creates an ImportJob and returns 202 Accepted."""
    auth_ctx = _mock_context("hr")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    csv_data = _generate_valid_csv(num_rows=3)
    files = {"file": ("staff_import.csv", csv_data, "text/csv")}

    with patch("services.workers.tasks.process_bulk_employee_import_task.delay") as mock_delay:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/v1/employees/import", files=files)

        assert res.status_code == 202
        body = res.json()
        assert body["file_name"] == "staff_import.csv"
        assert body["file_format"] == "csv"
        assert body["status"] == "queued"
        assert body["total_rows"] == 3
        assert mock_delay.called

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_xlsx_creates_import_job():
    """Verify uploading a valid XLSX file works properly."""
    auth_ctx = _mock_context("admin")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    xlsx_data = _generate_valid_xlsx(num_rows=2)
    files = {
        "file": (
            "employees.xlsx",
            xlsx_data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    with patch("services.workers.tasks.process_bulk_employee_import_task.delay"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/v1/employees/import", files=files)

        assert res.status_code == 202
        body = res.json()
        assert body["file_format"] == "xlsx"
        assert body["total_rows"] == 2

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_malformed_file_rejected():
    """Verify malformed content is rejected immediately with 400."""
    auth_ctx = _mock_context("owner")
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    files = {"file": ("corrupt.xlsx", b"not-a-valid-zip-or-excel", "application/octet-stream")}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/api/v1/employees/import", files=files)

    assert res.status_code == 400
    assert "Malformed" in res.json()["detail"] or "Missing" in res.json()["detail"]

    app.dependency_overrides.clear()


# ===========================================================================
# 5. Background Chunk Processing and Validation Engine Tests
# ===========================================================================


@pytest.mark.asyncio
async def test_process_import_job_chunks_with_valid_and_invalid_rows():
    """
    Test bulk processing of rows with:
    - Valid row -> Employee inserted
    - Bad email -> Error recorded
    - Bad date -> Error recorded
    - Invalid department -> Error recorded
    - Duplicate within file -> Error recorded
    - Error report CSV generated and uploaded
    """
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # Create CSV with 5 rows:
    # Row 1: Valid
    # Row 2: Invalid email
    # Row 3: Invalid date
    # Row 4: Duplicate of Row 1 employee ID
    # Row 5: Inactive or unknown department
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
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
    ])
    writer.writerow([
        "EMP-OK",
        "Alice",
        "Valid",
        "alice@corp.test",
        "+1-555-1111",
        "ENG",
        "DEV",
        "",
        "full_time",
        "2024-01-01",
        "HQ",
    ])
    writer.writerow([
        "EMP-BAD-EMAIL",
        "Bob",
        "Invalid",
        "not-an-email",
        "",
        "ENG",
        "DEV",
        "",
        "full_time",
        "2024-01-01",
        "HQ",
    ])
    writer.writerow([
        "EMP-BAD-DATE",
        "Charlie",
        "Invalid",
        "charlie@corp.test",
        "",
        "ENG",
        "DEV",
        "",
        "full_time",
        "not-a-date",
        "HQ",
    ])
    writer.writerow([
        "EMP-OK",
        "Alice2",
        "Duplicate",
        "alice2@corp.test",
        "",
        "ENG",
        "DEV",
        "",
        "full_time",
        "2024-01-01",
        "HQ",
    ])
    writer.writerow([
        "EMP-BAD-DEPT",
        "David",
        "Invalid",
        "david@corp.test",
        "",
        "NON_EXISTENT_DEPT",
        "DEV",
        "",
        "full_time",
        "2024-01-01",
        "HQ",
    ])
    csv_bytes = output.getvalue().encode("utf-8")

    # Store file in storage service
    file_key = storage_service.get_tenant_import_path(tenant_id, job_id, "test.csv")
    storage_service.upload_file(file_key, csv_bytes, content_type="text/csv")

    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        file_name="test.csv",
        file_format="csv",
        status="queued",
        total_rows=5,
        s3_file_key=file_key,
    )

    dept = Department(id=uuid.uuid4(), tenant_id=tenant_id, code="ENG", name="Engineering", is_active=True)
    desig = Designation(id=uuid.uuid4(), tenant_id=tenant_id, code="DEV", title="Developer", is_active=True)
    loc = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="HQ",
        name="Headquarters",
        address_line1="123 Main St",
        city="City",
        country_code="US",
        latitude=37.7749,
        longitude=-122.4194,
        radius_meters=100,
        timezone="UTC",
        is_active=True,
    )

    # Set up mock session
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.execute = AsyncMock()

    # Configure query results
    def execute_side_effect(statement, *args, **kwargs):
        stmt_str = str(statement)
        mock_result = MagicMock()
        if "FROM import_jobs" in stmt_str:
            mock_result.scalar_one_or_none.return_value = job
        elif "FROM departments" in stmt_str:
            mock_result.scalars.return_value = [dept]
        elif "FROM designations" in stmt_str:
            mock_result.scalars.return_value = [desig]
        elif "FROM locations" in stmt_str:
            mock_result.scalars.return_value = [loc]
        elif "FROM employees" in stmt_str:
            mock_result.scalars.return_value = []
        else:
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value = []
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    with patch("services.api.employees.import_service.AsyncSessionLocal") as mock_session_maker:
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        result = await process_import_job_chunks(job_id, tenant_id)

    assert result["status"] == "completed"
    assert result["total_rows"] == 5
    assert result["succeeded_rows"] == 1
    assert result["failed_rows"] == 4
    assert job.status == "completed"
    assert job.s3_error_key is not None


@pytest.mark.asyncio
async def test_checkpointing_and_retry_idempotency():
    """
    Verify that an interrupted import job:
    1. Keeps last_processed_row_index committed.
    2. Retry endpoint allows restarting queued job.
    3. Resumes from last_processed_row_index without re-processing prior rows.
    """
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # Create CSV with 150 rows
    csv_bytes = _generate_valid_csv(num_rows=150)
    file_key = storage_service.get_tenant_import_path(tenant_id, job_id, "checkpoint.csv")
    storage_service.upload_file(file_key, csv_bytes, content_type="text/csv")

    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        file_name="checkpoint.csv",
        file_format="csv",
        status="queued",
        total_rows=150,
        processed_rows=100,
        last_processed_row_index=100,  # Already processed first 100 rows
        succeeded_rows=100,
        failed_rows=0,
        s3_file_key=file_key,
    )

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    dept = Department(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="ENG",
        name="Engineering",
        is_active=True,
    )
    desig = Designation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="SE",
        title="Software Engineer",
        is_active=True,
    )
    loc = Location(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code="HQ",
        name="Headquarters",
        address_line1="123 Main St",
        city="City",
        country_code="US",
        latitude=37.7749,
        longitude=-122.4194,
        radius_meters=100,
        timezone="UTC",
        is_active=True,
    )

    def execute_side_effect(statement, *args, **kwargs):
        stmt_str = str(statement)
        mock_result = MagicMock()
        if "FROM import_jobs" in stmt_str:
            mock_result.scalar_one_or_none.return_value = job
        elif "FROM departments" in stmt_str:
            mock_result.scalars.return_value = [dept]
        elif "FROM designations" in stmt_str:
            mock_result.scalars.return_value = [desig]
        elif "FROM locations" in stmt_str:
            mock_result.scalars.return_value = [loc]
        elif "FROM employees" in stmt_str:
            mock_result.scalars.return_value = []
        else:
            mock_result.scalars.return_value = []
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    with patch("services.api.employees.import_service.AsyncSessionLocal") as mock_session_maker:
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        result = await process_import_job_chunks(job_id, tenant_id)

    assert result["status"] == "completed"
    # Started from 100, processed 50 more
    assert job.processed_rows == 150
    assert job.succeeded_rows == 150
    assert job.failed_rows == 0


# ===========================================================================
# 6. Tenant Isolation Tests on Import Endpoints
# ===========================================================================


@pytest.mark.asyncio
async def test_tenant_isolation_on_import_status_and_retry():
    """Verify Tenant A cannot view or retry Tenant B's import job (404 isolation)."""
    tenant_a_id = uuid.uuid4()
    job_id = uuid.uuid4()

    # User in Tenant A
    auth_ctx = _mock_context("owner", tenant_id=tenant_a_id)
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    mock_db = AsyncMock()
    # Query for job in Tenant A returns None (because job belongs to Tenant B)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /import/{job_id} -> 404
        res_get = await client.get(f"/api/v1/employees/import/{job_id}")
        assert res_get.status_code == 404
        assert "not found" in res_get.json()["detail"]

        # GET /import/{job_id}/errors -> 404
        res_err = await client.get(f"/api/v1/employees/import/{job_id}/errors")
        assert res_err.status_code == 404

        # POST /import/{job_id}/retry -> 404
        res_retry = await client.post(f"/api/v1/employees/import/{job_id}/retry")
        assert res_retry.status_code == 404

    app.dependency_overrides.clear()


# ===========================================================================
# 7. Celery Task Smoke Integration Test
# ===========================================================================


def test_celery_task_registration_and_execution():
    """Verify Celery task executes and handles errors gracefully."""
    with patch("services.api.employees.import_service.process_import_job_chunks") as mock_chunks:
        mock_chunks.return_value = {"status": "completed", "total_rows": 10}
        result = process_bulk_employee_import_task(str(uuid.uuid4()), str(uuid.uuid4()))
        assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_error_report_download_and_api():
    """Verify error report details and downloadable CSV endpoint."""
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()
    auth_ctx = _mock_context("hr", tenant_id=tenant_id)
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    err_key = storage_service.get_tenant_error_report_path(tenant_id, job_id)
    storage_service.upload_file(err_key, b"Row Number,Employee ID,Work Email,Errors\n2,EMP-1,,Email required\n", "text/csv")

    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        file_name="import.csv",
        file_format="csv",
        status="completed",
        total_rows=1,
        processed_rows=1,
        succeeded_rows=0,
        failed_rows=1,
        s3_file_key=f"tenants/{tenant_id}/imports/{job_id}/import.csv",
        s3_error_key=err_key,
        error_summary=[{"row_number": 2, "employee_id": "EMP-1", "work_email": None, "errors": ["Email required"]}],
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = job
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET errors summary
        res = await client.get(f"/api/v1/employees/import/{job_id}/errors")
        assert res.status_code == 200
        data = res.json()
        assert data["total_failed_rows"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["employee_id"] == "EMP-1"
        assert "download_url" in data

        # GET download CSV
        res_dl = await client.get(f"/api/v1/employees/import/{job_id}/errors/download")
        assert res_dl.status_code == 200
        assert b"Email required" in res_dl.content

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_retry_endpoint_behavior():
    """Verify retry transitions status to queued for incomplete jobs and rejects completed jobs."""
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()
    auth_ctx = _mock_context("admin", tenant_id=tenant_id)
    app.dependency_overrides[get_authenticated_context] = lambda: auth_ctx

    # Incomplete job
    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        file_name="import.csv",
        file_format="csv",
        status="failed",
        total_rows=10,
        processed_rows=5,
        last_processed_row_index=5,
        s3_file_key=f"tenants/{tenant_id}/imports/{job_id}/import.csv",
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = job
    mock_db.execute.return_value = mock_res
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("services.workers.tasks.process_bulk_employee_import_task.delay") as mock_delay:
            res = await client.post(f"/api/v1/employees/import/{job_id}/retry")
            assert res.status_code == 200
            assert res.json()["status"] == "queued"
            assert res.json()["resumed_from_row_index"] == 5
            assert mock_delay.called

        # Completed job rejection
        job.status = "completed"
        job.processed_rows = 10
        res_conflict = await client.post(f"/api/v1/employees/import/{job_id}/retry")
        assert res_conflict.status_code == 400
        assert "already finished" in res_conflict.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_database_duplicate_conflict_detected():
    """Verify row conflicting with existing DB employee is rejected and flagged."""
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["employee_id", "first_name", "last_name", "work_email", "joining_date"])
    writer.writerow(["EXISTING-01", "John", "Doe", "john.doe@corp.test", "2024-01-01"])
    csv_bytes = output.getvalue().encode("utf-8")

    file_key = storage_service.get_tenant_import_path(tenant_id, job_id, "dup.csv")
    storage_service.upload_file(file_key, csv_bytes, content_type="text/csv")

    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        file_name="dup.csv",
        file_format="csv",
        status="queued",
        total_rows=1,
        s3_file_key=file_key,
    )

    existing_emp = Employee(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        employee_id="EXISTING-01",
        first_name="John",
        last_name="Doe",
        work_email="john.doe@corp.test",
        joining_date=date(2023, 1, 1),
        status="active",
    )

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    def execute_side_effect(statement, *args, **kwargs):
        stmt_str = str(statement)
        mock_result = MagicMock()
        if "FROM import_jobs" in stmt_str:
            mock_result.scalar_one_or_none.return_value = job
        elif "FROM employees" in stmt_str:
            mock_result.scalars.return_value = [existing_emp]
        else:
            mock_result.scalars.return_value = []
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    mock_session.execute.side_effect = execute_side_effect

    with patch("services.api.employees.import_service.AsyncSessionLocal") as mock_session_maker:
        mock_session_maker.return_value.__aenter__.return_value = mock_session
        result = await process_import_job_chunks(job_id, tenant_id)

    assert result["status"] == "completed"
    assert result["failed_rows"] == 1
    assert result["succeeded_rows"] == 0
    assert any("already exists" in err for err in job.error_summary[0]["errors"])


@pytest.mark.asyncio
async def test_duplicate_column_headers_rejected():
    """Verify CSV with duplicate header names is rejected with 400."""
    csv_content = b"employee_id,first_name,first_name,work_email,joining_date\nEMP-1,John,Doe,john@test.com,2024-01-01\n"
    with pytest.raises(Exception) as exc_info:
        parse_import_file(csv_content, "dupe_headers.csv")
    assert "Duplicate column header" in str(exc_info.value)


@pytest.mark.asyncio
async def test_formula_injection_sanitization():
    """Verify cells starting with formula trigger chars (=, +, -, @) are sanitized."""
    csv_content = b"employee_id,first_name,last_name,work_email,joining_date\n=CMD('calc'),+John,@Doe,clean@test.com,2024-01-01\n"
    _, rows = parse_import_file(csv_content, "formula.csv")
    assert len(rows) == 1
    # Leading '=', '+', '@' must be stripped
    assert rows[0]["employee_id"] == "CMD('calc')"
    assert rows[0]["first_name"] == "John"
    assert rows[0]["last_name"] == "Doe"


@pytest.mark.asyncio
async def test_celery_dispatch_failure_returns_503():
    """Verify broker failure sets job status to failed and returns 503."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    context = _mock_context(role="hr", tenant_id=tenant_id, user_id=user_id)

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    app.dependency_overrides[get_authenticated_context] = lambda: context
    app.dependency_overrides[get_db] = lambda: mock_db

    csv_bytes = _generate_valid_csv(num_rows=2)
    files = {"file": ("employees.csv", io.BytesIO(csv_bytes), "text/csv")}

    with patch(
        "services.workers.tasks.process_bulk_employee_import_task.delay",
        side_effect=Exception("RabbitMQ / Redis broker connection timeout"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/v1/employees/import", files=files)

        assert res.status_code == 503
        data = res.json()
        assert "Background task queue is temporarily unavailable" in data["detail"]
        assert "recorded and can be retried" in data["detail"]
        assert mock_db.commit.called

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_retry_conflict_rejected():
    """Verify retrying a job that is already processing returns 409 Conflict."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    context = _mock_context(role="admin", tenant_id=tenant_id, user_id=user_id)
    app.dependency_overrides[get_authenticated_context] = lambda: context

    job_id = uuid.uuid4()
    processing_job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        file_name="active.csv",
        file_format="csv",
        status="processing",
        total_rows=10,
        processed_rows=5,
        s3_file_key=f"tenants/{tenant_id}/imports/{job_id}/active.csv",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = processing_job
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()

    app.dependency_overrides[get_db] = lambda: mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(f"/api/v1/employees/import/{job_id}/retry")

    assert res.status_code == 409
    assert "currently being processed" in res.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_tenant_storage_isolation_on_error_download():
    """Verify accessing error report with foreign tenant path returns 403."""
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    context = _mock_context(role="admin", tenant_id=tenant_id, user_id=user_id)
    app.dependency_overrides[get_authenticated_context] = lambda: context

    job_id = uuid.uuid4()
    tampered_job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        file_name="tampered.csv",
        file_format="csv",
        status="failed",
        total_rows=10,
        processed_rows=10,
        s3_error_key=f"tenants/{other_tenant_id}/imports/{job_id}/errors.csv",  # foreign tenant!
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tampered_job
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(f"/api/v1/employees/import/{job_id}/errors/download")

    assert res.status_code == 403
    assert "outside your tenant" in res.json()["detail"]

    app.dependency_overrides.clear()


def test_storage_service_production_requires_durable_s3():
    """Verify that in production without memory fallback, missing S3 raises RuntimeError on upload."""
    from services.api.common.storage import StorageService

    with patch("services.api.common.storage.settings") as mock_settings:
        mock_settings.ENVIRONMENT = "production"
        mock_settings.STORAGE_ALLOW_MEMORY_FALLBACK = False
        mock_settings.STORAGE_BUCKET = "test-bucket"

        service = StorageService()
        with patch.object(service, "_get_client", side_effect=Exception("S3 Connection Refused")):
            with pytest.raises(RuntimeError) as exc_info:
                service.upload_file("tenants/test/file.csv", b"test")

        assert "Production environments require configured S3/MinIO" in str(exc_info.value)


