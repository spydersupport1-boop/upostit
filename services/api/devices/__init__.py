"""Device binding domain package."""

from services.api.devices.models import Device
from services.api.devices.routes import router

__all__ = ["Device", "router"]

