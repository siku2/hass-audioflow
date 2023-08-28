import asyncio
import logging
from collections.abc import AsyncIterator
from ipaddress import IPv4Interface
from typing import Any

import voluptuous as vol
from homeassistant.components.network import async_get_adapters
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_BASE
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


ERROR_CONNECTION_FAILED = "connection"
ERROR_INVALID_URL = "invalid_url"
ERROR_NO_DISCOVERIES = "no_discoveries"

_DISCOVERY_TIMEOUT = 5.0


class AudioflowConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._discoveries: list[api.DiscoveryInfo] | None = None
        self._tasks: list[asyncio.Task[Any]] = []

    @callback
    def async_remove(self) -> None:
        for task in self._tasks:
            task.cancel("flow has been removed")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["manual", "auto_discover"]
        )

    async def async_step_manual(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        no_discoveries_made: bool = False,
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if no_discoveries_made:
            errors[CONF_BASE] = ERROR_NO_DISCOVERIES

        if user_input is not None:
            info = await self._get_info(user_input[CONF_BASE_URL], errors=errors)
            if info:
                return self.async_create_entry(title=info["title"], data=info["data"])
        else:
            user_input = {CONF_BASE_URL: ""}

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL, default=user_input[CONF_BASE_URL]): str,
                }
            ),
            errors=errors,
        )

    async def async_step_auto_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if self._discoveries is None:

            async def inner() -> None:
                all_discoveries = await _collect_discoveries_all_interfaces(
                    self.hass, _DISCOVERY_TIMEOUT
                )
                self._discoveries = []
                hosts_seen: set[str] = set()
                serial_numbers_already_configured: set[str] = {
                    entry.unique_id
                    for entry in self.hass.config_entries.async_entries(self.handler)
                    if entry.unique_id
                }
                for discovery in all_discoveries:
                    if discovery.serial_number in serial_numbers_already_configured:
                        _LOGGER.debug(
                            "removing device that's already configured: %s", discovery
                        )
                        continue
                    if discovery.host in hosts_seen:
                        _LOGGER.debug(
                            "removing duplicate host discovery: %s", discovery
                        )
                        continue
                    hosts_seen.add(discovery.host)
                    self._discoveries.append(discovery)

                self._tasks.append(
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_configure(
                            flow_id=self.flow_id
                        )
                    )
                )

            self.hass.async_create_task(inner())
            return self.async_show_progress(
                step_id="auto_discover", progress_action="discover"
            )

        return self.async_show_progress_done(next_step_id="discovery_select")

    async def async_step_discovery_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._discoveries:
            return await self.async_step_manual(no_discoveries_made=True)

        errors: dict[str, str] = {}
        if user_input is not None:
            info = await self._get_info(user_input[CONF_BASE_URL], errors=errors)
            if info:
                return self.async_create_entry(title=info["title"], data=info["data"])

        return self.async_show_form(
            step_id="discovery_select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL): vol.In(
                        {
                            discovery.host: f"{discovery.model} ({discovery.serial_number})"
                            for discovery in self._discoveries
                        }
                    ),
                }
            ),
            errors=errors,
        )

    async def _get_info(
        self, base_url: str | URL, *, errors: dict[str, str]
    ) -> dict[str, Any] | None:
        try:
            base_url = URL(base_url)
        except Exception:
            errors[CONF_BASE_URL] = ERROR_INVALID_URL
            return None
        if not base_url.is_absolute():
            try:
                base_url = URL(f"http://{base_url}")
            except Exception:
                errors[CONF_BASE_URL] = ERROR_INVALID_URL
                return None
        elif base_url.scheme not in ("http", "https"):
            errors[CONF_BASE_URL] = ERROR_INVALID_URL
            return None

        client = api.Client(async_get_clientsession(self.hass), base_url)
        try:
            state = await client.full_state()
            serial_number = state.switch["serial"]
        except Exception as exc:
            _LOGGER.warning(f"failed to fetch full state for {base_url}", exc_info=exc)
            errors[CONF_BASE] = ERROR_CONNECTION_FAILED
            return None

        await self.async_set_unique_id(serial_number)
        self._abort_if_unique_id_configured()

        return {"title": state.switch["serial"], "data": {CONF_BASE_URL: str(base_url)}}


async def _iter_ipv4_interfaces(hass: HomeAssistant) -> AsyncIterator[IPv4Interface]:
    adapters = await async_get_adapters(hass)
    for adapter in adapters:
        if not adapter["enabled"]:
            continue
        for ip_info in adapter["ipv4"]:
            yield IPv4Interface(f"{ip_info['address']}/{ip_info['network_prefix']}")


async def _collect_discoveries_all_interfaces(
    hass: HomeAssistant, timeout: float
) -> list[api.DiscoveryInfo]:
    loop = asyncio.get_running_loop()
    collected: list[api.DiscoveryInfo] = []

    pending_tasks = 0
    cond = asyncio.Condition()

    async def inner(interface: IPv4Interface) -> None:
        nonlocal pending_tasks
        try:
            collected.extend(await api.discover_list(interface, timeout))
        finally:
            pending_tasks -= 1
            async with cond:
                cond.notify_all()

    async for interface in _iter_ipv4_interfaces(hass):
        _LOGGER.debug("scanning on interface: %s", interface)
        pending_tasks += 1
        loop.create_task(inner(interface))

    async with cond:
        await cond.wait_for(lambda: pending_tasks <= 0)
    return collected
