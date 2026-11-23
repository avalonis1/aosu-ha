"""Camera platform for Aosu Cameras (battery-safe snapshot view)."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AosuCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AosuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(AosuSnapshotCamera(coordinator, sn) for sn in coordinator.data)


class AosuSnapshotCamera(CoordinatorEntity[AosuCoordinator], Camera):
    """Displays the latest event/cover JPEG snapshot without waking battery cameras."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._sn = sn
        self._attr_unique_id = f"{sn}_camera"

    @property
    def _cam(self):
        return self.coordinator.data.get(self._sn)

    @property
    def device_info(self) -> DeviceInfo:
        cam = self._cam
        return DeviceInfo(
            identifiers={(DOMAIN, self._sn)},
            name=cam.name if cam else self._sn,
            manufacturer="Aosu",
            model=cam.model if cam else "Camera",
        )

    @property
    def available(self) -> bool:
        cam = self._cam
        return cam is not None and cam.online

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        cam = self._cam
        if not cam:
            return None
        return cam.last_snapshot_bytes
