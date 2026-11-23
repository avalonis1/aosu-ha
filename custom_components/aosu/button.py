"""Button platform for Aosu Cameras (wake-up, manual snapshot refresh)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    entities: list[ButtonEntity] = []
    for sn in coordinator.data:
        entities.append(AosuWakeupButton(coordinator, sn))
        entities.append(AosuRefreshButton(coordinator, sn))
    async_add_entities(entities)


class _AosuBaseButton(CoordinatorEntity[AosuCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator)
        self._sn = sn

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


class AosuWakeupButton(_AosuBaseButton):
    _attr_name = "Réveiller"
    _attr_icon = "mdi:power-standby"

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_wakeup"

    async def async_press(self) -> None:
        await self.coordinator.client.async_wakeup_device(self._sn)
        await self.coordinator.async_request_refresh()


class AosuRefreshButton(_AosuBaseButton):
    _attr_name = "Actualiser l'historique"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_refresh"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
