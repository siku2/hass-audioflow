import asyncio
import logging
from datetime import timedelta

import homeassistant.helpers.aiohttp_client
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config, HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AudioflowDeviceClient, AudioflowDeviceState
from .const import CONF_BASE_URL, DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})

    base_url: str = entry.data[CONF_BASE_URL]
    session = homeassistant.helpers.aiohttp_client.async_get_clientsession(hass)
    client = AudioflowDeviceClient(session, base_url)

    coordinator = AudioflowUpdateCoordinator(hass, client=client)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    for platform in PLATFORMS:
        hass.async_add_job(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    platform_unload_coros = (
        hass.config_entries.async_forward_entry_unload(entry, platform)
        for platform in PLATFORMS
    )
    unloaded = all(await asyncio.gather(*platform_unload_coros))

    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


class AudioflowUpdateCoordinator(DataUpdateCoordinator[AudioflowDeviceState]):
    client: AudioflowDeviceClient

    def __init__(self, hass: HomeAssistant, client: AudioflowDeviceClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.client = client

    async def _async_update_data(self) -> AudioflowDeviceState:
        try:
            return await self.client.full_state()
        except Exception as exc:
            _LOGGER.warning("failed to fetch state update", exc_info=exc)
            raise UpdateFailed() from exc
