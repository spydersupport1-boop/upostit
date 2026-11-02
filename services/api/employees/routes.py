"""API routes for employee management under /api/v1/employees."""

import logging
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.common.storage import storage_service
from services.api.database import get_db
from services.api.employees.import_schemas import (
    ImportErrorsResponse,
    ImportJobResponse,
    ImportRetryResponse,
)
from services.api.employees.import_service import (
    download_import_job_error_report,
    generate_import_template_csv,
    get_import_job,
    get_import_job_errors,
    parse_import_file,
    retry_import_job,
    to_import_job_response,
)
from services.api.employees.invitation_schemas import InvitationResponse
from services.api.employees.invitation_service import create_employee_invitation
from services.api.employees.models import ImportJob
from services.api.employees.schemas import (
    EmployeeCreateRequest,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeStatusUpdateRequest,
    EmployeeUpdateRequest,
)
from services.api.employees.service import (
    create_employee,
    get_employee,
    get_employee_by_user_id,
    list_employees,
    update_employee,
    update_employee_status,
)
from services.api.locations.assignment_service import (
    assign_workplace_to_employee,
    end_employee_workplace_assignment,
    get_my_workplaces,
    list_employee_workplaces,
    update_employee_workplace_assignment,
)
from services.api.locations.schemas import (
    EmployeeWorkplaceAssignRequest,
    EmployeeWorkplaceListResponse,
    EmployeeWorkplaceResponse,
    EmployeeWorkplaceUpdateRequest,
)

router = APIRouter(prefix="/employees", tags=["Employees"])
logger = logging.getLogger("attendance.api.employees")


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new employee profile",
    dependencies=[Depends(require_permission(Permission.CREATE_EMPLOYEES))],
)
async def create_employee_endpoint(
    req: EmployeeCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    return await create_employee(session, context.tenant.id, req)


@router.get(
    "",
    response_model=EmployeeListResponse,
    summary="List employees with search, multi-field filtering, and pagination",
    dependencies=[Depends(require_permission(Permission.VIEW_EMPLOYEES))],
)
async def list_employees_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[
        str | None, Query(description="Search by name, employee ID, or email")
    ] = None,
    department_id: Annotated[
        uuid.UUID | None, Query(description="Filter by department UUID")
    ] = None,
    designation_id: Annotated[
        uuid.UUID | None, Query(description="Filter by designation UUID")
    ] = None,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status", description="Filter by status (active, inactive, on_leave, terminated)"
        ),
    ] = None,
    employment_type: Annotated[str | None, Query(description="Filter by employment type")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> EmployeeListResponse:
    items, total = await list_employees(
        session=session,
        tenant_id=context.tenant.id,
        search=search,
        department_id=department_id,
        designation_id=designation_id,
        status_filter=status_filter,
        employment_type=employment_type,
        page=page,
        page_size=page_size,
    )
    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/me",
    response_model=EmployeeResponse,
    summary="Get authenticated employee's own profile",
    dependencies=[Depends(require_permission(Permission.VIEW_OWN_PROFILE))],
)
async def get_my_employee_profile_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    return await get_employee_by_user_id(session, context.tenant.id, context.user.id)


@router.get(
    "/me/workplaces",
    response_model=EmployeeWorkplaceListResponse,
    summary="Get authenticated employee's assigned workplaces",
    dependencies=[Depends(require_permission(Permission.VIEW_OWN_PROFILE))],
)
async def get_my_workplaces_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    is_current: Annotated[
        bool | None,
        Query(description="Filter by current active effectiveness"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
) -> EmployeeWorkplaceListResponse:
    items, total = await get_my_workplaces(
        session=session,
        tenant_id=context.tenant.id,
        user_id=context.user.id,
        is_current=is_current,
        page=page,
        page_size=page_size,
    )
    return EmployeeWorkplaceListResponse(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# Bulk Employee Import Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/import/template",
    summary="Download standardized bulk employee import CSV template",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def download_import_template_endpoint() -> Response:
    csv_content = generate_import_template_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employee_import_template.csv"'},
    )


@router.post(
    "/import",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload and enqueue bulk employee import job (CSV or XLSX)",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def import_employees_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[
        UploadFile, File(description="CSV or XLSX spreadsheet (max 10MB, max 2000 rows)")
    ],
) -> ImportJobResponse:
    # 1. Read file bytes
    file_bytes = await file.read()
    filename = file.filename or "import.csv"

    # 2. Content and header validation
    file_format, parsed_rows = parse_import_file(file_bytes, filename)

    # 3. Secure tenant-isolated storage upload
    job_id = uuid.uuid4()
    clean_filename = filename.replace("/", "_").replace("\\", "_")
    s3_key = storage_service.get_tenant_import_path(context.tenant.id, job_id, clean_filename)
    storage_service.upload_file(
        s3_key,
        file_bytes,
        content_type=file.content_type or "application/octet-stream",
    )

    # 4. Create import job record
    job = ImportJob(
        id=job_id,
        tenant_id=context.tenant.id,
        created_by_user_id=context.user.id,
        file_name=clean_filename,
        file_format=file_format,
        status="queued",
        total_rows=len(parsed_rows),
        processed_rows=0,
        succeeded_rows=0,
        failed_rows=0,
        last_processed_row_index=0,
        error_summary=[],
        s3_file_key=s3_key,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    # 5. Dispatch asynchronous background worker
    try:
        from services.workers.tasks import process_bulk_employee_import_task

        process_bulk_employee_import_task.delay(str(job.id), str(context.tenant.id))
    except Exception as exc:
        logger.exception("Failed to dispatch Celery import task for job %s: %s", job.id, exc)
        job.status = "failed"
        job.error_summary = [
            {"row_number": 0, "errors": [f"Background queue broker unavailable: {exc!s}. Job saved; retry is supported."]}
        ]
        await session.commit()
        await session.refresh(job)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Background task queue is temporarily unavailable. Import job {job.id} was recorded and can be retried.",
        )

    return to_import_job_response(job)


@router.get(
    "/import/{job_id}",
    response_model=ImportJobResponse,
    summary="Get status, counters, and progress of an import job",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def get_import_job_endpoint(
    job_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ImportJobResponse:
    return await get_import_job(session, context.tenant.id, job_id)


@router.get(
    "/import/{job_id}/errors",
    response_model=ImportErrorsResponse,
    summary="Get line-by-line error diagnostics for an import job",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def get_import_job_errors_endpoint(
    job_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ImportErrorsResponse:
    return await get_import_job_errors(session, context.tenant.id, job_id)


@router.get(
    "/import/{job_id}/errors/download",
    summary="Download failure CSV report for an import job",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def download_import_job_errors_endpoint(
    job_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    csv_bytes = await download_import_job_error_report(session, context.tenant.id, job_id)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import_errors_{job_id}.csv"'},
    )


@router.post(
    "/import/{job_id}/retry",
    response_model=ImportRetryResponse,
    summary="Safely retry an interrupted or failed import job from its last checkpoint",
    dependencies=[Depends(require_permission(Permission.IMPORT_EMPLOYEES))],
)
async def retry_import_job_endpoint(
    job_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ImportRetryResponse:
    retry_resp = await retry_import_job(session, context.tenant.id, job_id)
    try:
        from services.workers.tasks import process_bulk_employee_import_task

        process_bulk_employee_import_task.delay(str(job_id), str(context.tenant.id))
    except Exception as exc:
        logger.exception("Could not dispatch Celery task on retry for job %s: %s", job_id, exc)
        q = await session.execute(
            select(ImportJob).where(ImportJob.id == job_id, ImportJob.tenant_id == context.tenant.id)
        )
        j = q.scalar_one_or_none()
        if j:
            j.status = "failed"
            j.error_summary = [{"row_number": 0, "errors": [f"Retry queue dispatch failed: {exc!s}"]}]
            await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background task queue is temporarily unavailable for retry.",
        )
    return retry_resp


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
    summary="Get employee profile details by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_EMPLOYEES))],
)
async def get_employee_endpoint(
    employee_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    return await get_employee(session, context.tenant.id, employee_id)


@router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
    summary="Update an employee profile",
    dependencies=[Depends(require_permission(Permission.UPDATE_EMPLOYEES))],
)
async def update_employee_endpoint(
    employee_id: uuid.UUID,
    req: EmployeeUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    return await update_employee(session, context.tenant.id, employee_id, req)


@router.patch(
    "/{employee_id}/status",
    response_model=EmployeeResponse,
    summary="Update employee employment status",
    dependencies=[Depends(require_permission(Permission.DEACTIVATE_EMPLOYEES))],
)
async def update_employee_status_endpoint(
    employee_id: uuid.UUID,
    req: EmployeeStatusUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeResponse:
    return await update_employee_status(session, context.tenant.id, employee_id, req.status)


@router.post(
    "/{employee_id}/workplaces",
    response_model=EmployeeWorkplaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a workplace location to an employee",
    dependencies=[Depends(require_permission(Permission.UPDATE_EMPLOYEES))],
)
async def assign_employee_workplace_endpoint(
    employee_id: uuid.UUID,
    req: EmployeeWorkplaceAssignRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeWorkplaceResponse:
    return await assign_workplace_to_employee(
        session=session,
        tenant_id=context.tenant.id,
        employee_id=employee_id,
        data=req,
    )


@router.get(
    "/{employee_id}/workplaces",
    response_model=EmployeeWorkplaceListResponse,
    summary="List workplace assignments for an employee",
    dependencies=[Depends(require_permission(Permission.VIEW_EMPLOYEES))],
)
async def list_employee_workplaces_endpoint(
    employee_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    is_current: Annotated[
        bool | None,
        Query(description="Filter by current active effectiveness"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> EmployeeWorkplaceListResponse:
    items, total = await list_employee_workplaces(
        session=session,
        tenant_id=context.tenant.id,
        employee_id=employee_id,
        is_current=is_current,
        page=page,
        page_size=page_size,
    )
    return EmployeeWorkplaceListResponse(items=items, total=total, page=page, page_size=page_size)


@router.put(
    "/{employee_id}/workplaces/{assignment_id}",
    response_model=EmployeeWorkplaceResponse,
    summary="Update an employee's workplace assignment",
    dependencies=[Depends(require_permission(Permission.UPDATE_EMPLOYEES))],
)
async def update_employee_workplace_endpoint(
    employee_id: uuid.UUID,
    assignment_id: uuid.UUID,
    req: EmployeeWorkplaceUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> EmployeeWorkplaceResponse:
    return await update_employee_workplace_assignment(
        session=session,
        tenant_id=context.tenant.id,
        employee_id=employee_id,
        assignment_id=assignment_id,
        data=req,
    )


@router.delete(
    "/{employee_id}/workplaces/{assignment_id}",
    response_model=EmployeeWorkplaceResponse,
    summary="Safely end an employee's workplace assignment",
    dependencies=[Depends(require_permission(Permission.UPDATE_EMPLOYEES))],
)
async def end_employee_workplace_endpoint(
    employee_id: uuid.UUID,
    assignment_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    end_date: Annotated[
        date | None,
        Query(description="Effective end date (defaults to today)"),
    ] = None,
) -> EmployeeWorkplaceResponse:
    return await end_employee_workplace_assignment(
        session=session,
        tenant_id=context.tenant.id,
        employee_id=employee_id,
        assignment_id=assignment_id,
        end_date=end_date,
    )


@router.post(
    "/{employee_id}/invite",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite an existing employee to activate their account",
    dependencies=[Depends(require_permission(Permission.INVITE_EMPLOYEES))],
)
async def invite_employee_endpoint(
    employee_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationResponse:
    return await create_employee_invitation(
        session=session,
        tenant_id=context.tenant.id,
        employee_id=employee_id,
        current_user_id=context.user.id,
    )


