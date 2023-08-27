import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    base_url: str = entry.data[CONF_BASE_URL]
    coordinator = Coordinator(
        hass, client=api.Client(async_get_clientsession(hass), base_url)
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator: Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return ok


class Coordinator(DataUpdateCoordinator[api.FullState]):
    client: api.Client

    def __init__(self, hass: HomeAssistant, client: api.Client) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=60)
        )
        self.client = client

        self._device_info = None

    @property
    def device_info(self) -> DeviceInfo:
        assert self._device_info
        return self._device_info

    async def _async_update_data(self) -> api.FullState:
        try:
            return await self.client.full_state()
        except Exception as exc:
            _LOGGER.warning("failed to fetch state update", exc_info=exc)
            raise UpdateFailed() from exc

    async def async_config_entry_first_refresh(self) -> None:
        await super().async_config_entry_first_refresh()
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.data.switch["serial"])},
            name=self.data.switch["name"],
            model=self.data.switch["model"],
            manufacturer="Audioflow",
            sw_version=self.data.switch["version"],
        )
