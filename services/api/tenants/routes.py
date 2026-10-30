"""Tenant management and profile routes under /api/v1/tenants."""

from typing import Annotated

from fastapi import APIRouter, Depends

from services.api.auth.dependencies import get_current_tenant
from services.api.tenants.models import Tenant
from services.api.tenants.schemas import TenantResponse

router = APIRouter(prefix="/tenants", tags=["Tenants"])


@router.get(
    "/current",
    response_model=TenantResponse,
    summary="Get authenticated company tenant information",
)
async def get_current_tenant_profile(
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> TenantResponse:
    """Returns the company profile for the authenticated tenant context."""
    return TenantResponse.model_validate(tenant)
