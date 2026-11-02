"""API routes for departments and designations under /api/v1/departments and /api/v1/designations."""

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
from services.api.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
    DesignationCreateRequest,
    DesignationListResponse,
    DesignationResponse,
    DesignationUpdateRequest,
)
from services.api.organization.service import (
    create_department,
    create_designation,
    deactivate_department,
    deactivate_designation,
    get_department,
    get_designation,
    list_departments,
    list_designations,
    update_department,
    update_designation,
)

departments_router = APIRouter(prefix="/departments", tags=["Departments"])
designations_router = APIRouter(prefix="/designations", tags=["Designations"])


# ==============================================================================
# Department Endpoints
# ==============================================================================


@departments_router.post(
    "",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new department",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def create_department_endpoint(
    req: DepartmentCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    dept = await create_department(session, context.tenant.id, req)
    return DepartmentResponse.model_validate(dept)


@departments_router.get(
    "",
    response_model=DepartmentListResponse,
    summary="List departments with search and status filtering",
    dependencies=[Depends(require_permission(Permission.VIEW_ORGANIZATION))],
)
async def list_departments_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    is_active: Annotated[
        bool | None, Query(description="Filter active or inactive departments")
    ] = None,
    search: Annotated[str | None, Query(description="Search by name or code")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DepartmentListResponse:
    items, total = await list_departments(
        session, context.tenant.id, is_active=is_active, search=search, limit=limit, offset=offset
    )
    return DepartmentListResponse(
        items=[DepartmentResponse.model_validate(d) for d in items],
        total=total,
    )


@departments_router.get(
    "/{department_id}",
    response_model=DepartmentResponse,
    summary="Get department details by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_ORGANIZATION))],
)
async def get_department_endpoint(
    department_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    dept = await get_department(session, context.tenant.id, department_id)
    return DepartmentResponse.model_validate(dept)


@departments_router.put(
    "/{department_id}",
    response_model=DepartmentResponse,
    summary="Update department details",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def update_department_endpoint(
    department_id: uuid.UUID,
    req: DepartmentUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    dept = await update_department(session, context.tenant.id, department_id, req)
    return DepartmentResponse.model_validate(dept)


@departments_router.delete(
    "/{department_id}",
    response_model=DepartmentResponse,
    summary="Deactivate a department",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def deactivate_department_endpoint(
    department_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DepartmentResponse:
    dept = await deactivate_department(session, context.tenant.id, department_id)
    return DepartmentResponse.model_validate(dept)


# ==============================================================================
# Designation Endpoints
# ==============================================================================


@designations_router.post(
    "",
    response_model=DesignationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new designation",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def create_designation_endpoint(
    req: DesignationCreateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DesignationResponse:
    desig = await create_designation(session, context.tenant.id, req)
    return DesignationResponse.model_validate(desig)


@designations_router.get(
    "",
    response_model=DesignationListResponse,
    summary="List designations with search and status filtering",
    dependencies=[Depends(require_permission(Permission.VIEW_ORGANIZATION))],
)
async def list_designations_endpoint(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
    is_active: Annotated[
        bool | None, Query(description="Filter active or inactive designations")
    ] = None,
    search: Annotated[str | None, Query(description="Search by title or code")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DesignationListResponse:
    items, total = await list_designations(
        session, context.tenant.id, is_active=is_active, search=search, limit=limit, offset=offset
    )
    return DesignationListResponse(
        items=[DesignationResponse.model_validate(d) for d in items],
        total=total,
    )


@designations_router.get(
    "/{designation_id}",
    response_model=DesignationResponse,
    summary="Get designation details by ID",
    dependencies=[Depends(require_permission(Permission.VIEW_ORGANIZATION))],
)
async def get_designation_endpoint(
    designation_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DesignationResponse:
    desig = await get_designation(session, context.tenant.id, designation_id)
    return DesignationResponse.model_validate(desig)


@designations_router.put(
    "/{designation_id}",
    response_model=DesignationResponse,
    summary="Update designation details",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def update_designation_endpoint(
    designation_id: uuid.UUID,
    req: DesignationUpdateRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DesignationResponse:
    desig = await update_designation(session, context.tenant.id, designation_id, req)
    return DesignationResponse.model_validate(desig)


@designations_router.delete(
    "/{designation_id}",
    response_model=DesignationResponse,
    summary="Deactivate a designation",
    dependencies=[Depends(require_permission(Permission.MANAGE_ORGANIZATION))],
)
async def deactivate_designation_endpoint(
    designation_id: uuid.UUID,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DesignationResponse:
    desig = await deactivate_designation(session, context.tenant.id, designation_id)
    return DesignationResponse.model_validate(desig)
