from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import BridgeCoordinator

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the st_bridge component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the st_bridge component from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coord = BridgeCoordinator(hass, entry)
    await coord.async_start()

    @callback
    async def _update_listener(hass, entry):
        hass.loop.create_task(coord.async_handle_entry_update())

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    hass.data[DOMAIN][entry.entry_id] = coord
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coord: BridgeCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coord:
        await coord.async_stop()
    return True
