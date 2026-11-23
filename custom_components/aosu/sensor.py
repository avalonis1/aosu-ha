"""Sensor platform for Aosu Cameras (battery, Wi-Fi, last event, last recognized face)."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
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
    entities: list[SensorEntity] = []
    for sn, cam in coordinator.data.items():
        if cam.battery is not None:
            entities.append(AosuBatterySensor(coordinator, sn))
        entities.append(AosuWifiSensor(coordinator, sn))
        entities.append(AosuLastEventSensor(coordinator, sn))
        entities.append(AosuLastFaceSensor(coordinator, sn))
    async_add_entities(entities)


class _AosuBaseSensor(CoordinatorEntity[AosuCoordinator], SensorEntity):
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


class AosuBatterySensor(_AosuBaseSensor):
    _attr_name = "Batterie"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_battery"

    @property
    def native_value(self) -> int | None:
        return self._cam.battery if self._cam else None


class AosuWifiSensor(_AosuBaseSensor):
    _attr_name = "Signal Wi-Fi"
    _attr_icon = "mdi:wifi"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_wifi"

    @property
    def native_value(self) -> int | None:
        return self._cam.wifi_signal if self._cam else None


class AosuLastEventSensor(_AosuBaseSensor):
    _attr_name = "Dernier événement"
    _attr_icon = "mdi:motion-sensor"

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_last_event"

    @property
    def native_value(self) -> str | None:
        cam = self._cam
        if not cam or not cam.last_event_types:
            return None
        return ", ".join(cam.last_event_types)

    @property
    def extra_state_attributes(self) -> dict:
        cam = self._cam
        if not cam:
            return {}
        return {
            "event_time": cam.last_event_time,
            "event_types": cam.last_event_types,
            "recent_events": cam.recent_events,
            "backend": cam.svc_type,
        }


class AosuLastFaceSensor(_AosuBaseSensor):
    _attr_name = "Dernier visage reconnu"
    _attr_icon = "mdi:face-recognition"

    def __init__(self, coordinator: AosuCoordinator, sn: str) -> None:
        super().__init__(coordinator, sn)
        self._attr_unique_id = f"{sn}_last_face"

    @property
    def native_value(self) -> str | None:
        return self._cam.last_face_name if self._cam else None

    @property
    def extra_state_attributes(self) -> dict:
        cam = self._cam
        if not cam:
            return {}
        return {
            "confidence": cam.last_face_confidence,
            "event_time": cam.last_event_time,
        }
