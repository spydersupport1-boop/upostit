"""Business logic service for departments and designations."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.organization.models import Department, Designation
from services.api.organization.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    DesignationCreateRequest,
    DesignationUpdateRequest,
)

# ==============================================================================
# Department Services
# ==============================================================================


async def create_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: DepartmentCreateRequest,
) -> Department:
    """Creates a new department within the tenant organization."""
    clean_name = req.name.strip()
    clean_code = req.code.strip().upper()

    # 1. Uniqueness check within tenant for code
    res_code = await session.execute(
        select(Department).where(
            Department.tenant_id == tenant_id,
            Department.code == clean_code,
        )
    )
    if res_code.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Department with code '{clean_code}' already exists in your organization",
        )

    # 2. Uniqueness check within tenant for name
    res_name = await session.execute(
        select(Department).where(
            Department.tenant_id == tenant_id,
            func.lower(Department.name) == clean_name.lower(),
        )
    )
    if res_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Department with name '{clean_name}' already exists in your organization",
        )

    # 3. Manager foreign key verification (if manager_id provided, must belong to same tenant)
    if req.manager_id:
        from services.api.employees.models import Employee

        mgr_res = await session.execute(
            select(Employee).where(
                Employee.id == req.manager_id,
                Employee.tenant_id == tenant_id,
                Employee.status == "active",
            )
        )
        if not mgr_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected manager does not exist or does not belong to your organization",
            )

    dept = Department(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=clean_name,
        code=clean_code,
        description=req.description.strip() if req.description else None,
        manager_id=req.manager_id,
        is_active=True,
    )
    session.add(dept)
    await session.commit()
    await session.refresh(dept)
    return dept


async def list_departments(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Department], int]:
    """Lists departments for the tenant with optional search and active filtering."""
    query = select(Department).where(Department.tenant_id == tenant_id)
    count_query = (
        select(func.count()).select_from(Department).where(Department.tenant_id == tenant_id)
    )

    if is_active is not None:
        query = query.where(Department.is_active == is_active)
        count_query = count_query.where(Department.is_active == is_active)

    if search:
        search_pattern = f"%{search.strip()}%"
        cond = or_(
            Department.name.ilike(search_pattern),
            Department.code.ilike(search_pattern),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total_res = await session.execute(count_query)
    total = total_res.scalar_one()

    query = query.order_by(Department.name.asc()).limit(limit).offset(offset)
    items_res = await session.execute(query)
    items = list(items_res.scalars().all())

    return items, total


async def get_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dept_id: uuid.UUID,
) -> Department:
    """Retrieves department details by ID within the tenant scope."""
    res = await session.execute(
        select(Department).where(
            Department.id == dept_id,
            Department.tenant_id == tenant_id,
        )
    )
    dept = res.scalar_one_or_none()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )
    return dept


async def update_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dept_id: uuid.UUID,
    req: DepartmentUpdateRequest,
) -> Department:
    """Updates an existing department."""
    dept = await get_department(session, tenant_id, dept_id)

    if req.name is not None:
        clean_name = req.name.strip()
        if clean_name.lower() != dept.name.lower():
            res_name = await session.execute(
                select(Department).where(
                    Department.tenant_id == tenant_id,
                    func.lower(Department.name) == clean_name.lower(),
                    Department.id != dept_id,
                )
            )
            if res_name.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Department with name '{clean_name}' already exists in your organization",
                )
            dept.name = clean_name

    if req.code is not None:
        clean_code = req.code.strip().upper()
        if clean_code != dept.code:
            res_code = await session.execute(
                select(Department).where(
                    Department.tenant_id == tenant_id,
                    Department.code == clean_code,
                    Department.id != dept_id,
                )
            )
            if res_code.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Department with code '{clean_code}' already exists in your organization",
                )
            dept.code = clean_code

    if req.description is not None:
        dept.description = req.description.strip() if req.description else None

    if req.manager_id is not None:
        from services.api.employees.models import Employee

        mgr_res = await session.execute(
            select(Employee).where(
                Employee.id == req.manager_id,
                Employee.tenant_id == tenant_id,
                Employee.status == "active",
            )
        )
        if not mgr_res.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected manager does not exist or does not belong to your organization",
            )
        dept.manager_id = req.manager_id

    if req.is_active is not None:
        dept.is_active = req.is_active

    dept.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(dept)
    return dept


async def deactivate_department(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    dept_id: uuid.UUID,
) -> Department:
    """Soft-deactivates a department."""
    dept = await get_department(session, tenant_id, dept_id)
    dept.is_active = False
    dept.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(dept)
    return dept


# ==============================================================================
# Designation Services
# ==============================================================================


async def create_designation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    req: DesignationCreateRequest,
) -> Designation:
    """Creates a new designation within the tenant organization."""
    clean_title = req.title.strip()
    clean_code = req.code.strip().upper()

    # 1. Uniqueness check for code
    res_code = await session.execute(
        select(Designation).where(
            Designation.tenant_id == tenant_id,
            Designation.code == clean_code,
        )
    )
    if res_code.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Designation with code '{clean_code}' already exists in your organization",
        )

    # 2. Uniqueness check for title
    res_title = await session.execute(
        select(Designation).where(
            Designation.tenant_id == tenant_id,
            func.lower(Designation.title) == clean_title.lower(),
        )
    )
    if res_title.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Designation with title '{clean_title}' already exists in your organization",
        )

    desig = Designation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        title=clean_title,
        code=clean_code,
        description=req.description.strip() if req.description else None,
        is_active=True,
    )
    session.add(desig)
    await session.commit()
    await session.refresh(desig)
    return desig


async def list_designations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    is_active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Designation], int]:
    """Lists designations for the tenant with optional search and active filtering."""
    query = select(Designation).where(Designation.tenant_id == tenant_id)
    count_query = (
        select(func.count()).select_from(Designation).where(Designation.tenant_id == tenant_id)
    )

    if is_active is not None:
        query = query.where(Designation.is_active == is_active)
        count_query = count_query.where(Designation.is_active == is_active)

    if search:
        search_pattern = f"%{search.strip()}%"
        cond = or_(
            Designation.title.ilike(search_pattern),
            Designation.code.ilike(search_pattern),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total_res = await session.execute(count_query)
    total = total_res.scalar_one()

    query = query.order_by(Designation.title.asc()).limit(limit).offset(offset)
    items_res = await session.execute(query)
    items = list(items_res.scalars().all())

    return items, total


async def get_designation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    desig_id: uuid.UUID,
) -> Designation:
    """Retrieves designation details by ID within tenant scope."""
    res = await session.execute(
        select(Designation).where(
            Designation.id == desig_id,
            Designation.tenant_id == tenant_id,
        )
    )
    desig = res.scalar_one_or_none()
    if not desig:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designation not found",
        )
    return desig


async def update_designation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    desig_id: uuid.UUID,
    req: DesignationUpdateRequest,
) -> Designation:
    """Updates an existing designation."""
    desig = await get_designation(session, tenant_id, desig_id)

    if req.title is not None:
        clean_title = req.title.strip()
        if clean_title.lower() != desig.title.lower():
            res_title = await session.execute(
                select(Designation).where(
                    Designation.tenant_id == tenant_id,
                    func.lower(Designation.title) == clean_title.lower(),
                    Designation.id != desig_id,
                )
            )
            if res_title.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Designation with title '{clean_title}' already exists in your organization",
                )
            desig.title = clean_title

    if req.code is not None:
        clean_code = req.code.strip().upper()
        if clean_code != desig.code:
            res_code = await session.execute(
                select(Designation).where(
                    Designation.tenant_id == tenant_id,
                    Designation.code == clean_code,
                    Designation.id != desig_id,
                )
            )
            if res_code.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Designation with code '{clean_code}' already exists in your organization",
                )
            desig.code = clean_code

    if req.description is not None:
        desig.description = req.description.strip() if req.description else None

    if req.is_active is not None:
        desig.is_active = req.is_active

    desig.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(desig)
    return desig


async def deactivate_designation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    desig_id: uuid.UUID,
) -> Designation:
    """Soft-deactivates a designation."""
    desig = await get_designation(session, tenant_id, desig_id)
    desig.is_active = False
    desig.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(desig)
    return desig
