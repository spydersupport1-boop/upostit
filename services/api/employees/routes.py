"""API routes for employee management under /api/v1/employees."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.auth.dependencies import (
    AuthenticatedContext,
    get_authenticated_context,
    require_permission,
)
from services.api.auth.permissions import Permission
from services.api.database import get_db
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

router = APIRouter(prefix="/employees", tags=["Employees"])


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
    search: Annotated[str | None, Query(description="Search by name, employee ID, or email")] = None,
    department_id: Annotated[uuid.UUID | None, Query(description="Filter by department UUID")] = None,
    designation_id: Annotated[uuid.UUID | None, Query(description="Filter by designation UUID")] = None,
    status_filter: Annotated[str | None, Query(alias="status", description="Filter by status (active, inactive, on_leave, terminated)")] = None,
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
