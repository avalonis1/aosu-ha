"""The Aosu Cameras integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import AsyncAosuClient
from .const import (
    CONF_COMPREFACE_API_KEY,
    CONF_COMPREFACE_URL,
    CONF_EMAIL,
    CONF_FACE_THRESHOLD,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_FACE_THRESHOLD,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AosuCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aosu Cameras from a config entry."""
    client = AsyncAosuClient(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        region=entry.data.get(CONF_REGION, DEFAULT_REGION),
    )
    await client.async_login()

    opts = entry.options
    coordinator = AosuCoordinator(
        hass=hass,
        client=client,
        scan_interval=int(opts.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
        compreface_url=str(opts.get(CONF_COMPREFACE_URL, entry.data.get(CONF_COMPREFACE_URL, ""))),
        compreface_api_key=str(opts.get(CONF_COMPREFACE_API_KEY, entry.data.get(CONF_COMPREFACE_API_KEY, ""))),
        face_threshold=float(opts.get(CONF_FACE_THRESHOLD, entry.data.get(CONF_FACE_THRESHOLD, DEFAULT_FACE_THRESHOLD))),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: AosuCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
    return unload_ok
