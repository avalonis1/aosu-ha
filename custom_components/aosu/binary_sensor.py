"""Binary sensor platform for Aosu Cameras (online, person detected, doorbell ring)."""

from __future__ import annotations

import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AosuCoordinator

ACTIVE_WINDOW_MS = 120_000  # 2 minutes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: AosuCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = []
    for sn, cam in coordinator.data.items():
        entities.append(AosuOnlineBinarySensor(coordinator, sn))
        entities.append(AosuPersonBinarySensor(coordinator, sn))
        if cam.dev_type == 1:  # Video doorbell
            entities.append(AosuDoorbellBinarySensor(coordinator, sn))
    async_add_entities(entities)


class _AosuBaseBinarySensor(CoordinatorEntity[AosuCoordinator], BinarySensorEntity):
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


class AosuOnlineBinarySensor(_AosuBaseBinarySensor):
    _attr_name = "En ligne"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_online"

    @property
    def is_on(self) -> bool:
        return bool(self._cam and self._cam.online)


class AosuPersonBinarySensor(_AosuBaseBinarySensor):
    _attr_name = "Personne détectée"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_person"

    @property
    def is_on(self) -> bool:
        cam = self._cam
        if not cam or not cam.last_event_time or "person" not in cam.last_event_types:
            return False
        now_ms = int(time.time() * 1000)
        return (now_ms - cam.last_event_time) <= ACTIVE_WINDOW_MS


class AosuDoorbellBinarySensor(_AosuBaseBinarySensor):
    _attr_name = "Sonnette"
    _attr_device_class = BinarySensorDeviceClass.SOUND
    _attr_icon = "mdi:doorbell-video"

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_doorbell"

    @property
    def is_on(self) -> bool:
        cam = self._cam
        if not cam or not cam.last_event_time or "ring" not in cam.last_event_types:
            return False
        now_ms = int(time.time() * 1000)
        return (now_ms - cam.last_event_time) <= ACTIVE_WINDOW_MS
