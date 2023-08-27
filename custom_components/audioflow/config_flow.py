import contextlib
import logging
from typing import Any

import homeassistant.helpers.aiohttp_client
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AudioflowConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _errors: dict[str, str]

    def __init__(self) -> None:
        super().__init__()
        self._errors = {}

    def _coerce_base_url(self, raw_url: str) -> URL | None:
        try:
            url = URL(raw_url)
        except Exception:
            self._errors[CONF_BASE_URL] = "invalid_url"
            return None

        if not url.is_absolute():
            try:
                url = URL(f"http://{raw_url}")
            except Exception:
                self._errors[CONF_BASE_URL] = "invalid_url"
                return None
        elif url.scheme not in ("http", "https"):
            self._errors[CONF_BASE_URL] = "invalid_url"
            return None

        with contextlib.suppress(KeyError):
            del self._errors[CONF_BASE_URL]
        return url

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            valid = False
            base_url = self._coerce_base_url(user_input[CONF_BASE_URL])
            if base_url is not None:
                valid = await self._test_base_url(base_url)

            if valid:
                assert base_url
                # make sure to store the coerced base url
                user_input[CONF_BASE_URL] = str(base_url)
                title = base_url.host or str(base_url)
                return self.async_create_entry(title=title, data=user_input)

            self._errors["base"] = "connection"
            return await self._show_config_form(user_input)

        user_input = {}
        user_input[CONF_BASE_URL] = ""

        return await self._show_config_form(user_input)

    async def _show_config_form(self, user_input: dict[str, Any]) -> FlowResult:
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BASE_URL, default=user_input[CONF_BASE_URL]): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_base_url(self, base_url: URL) -> bool:
        _LOGGER.info("testing base URL: %s", base_url)
        try:
            session = homeassistant.helpers.aiohttp_client.async_create_clientsession(
                self.hass
            )
            client = api.Client(session, base_url)
            await client.full_state()
            return True
        except Exception as exc:
            _LOGGER.warning("test failed", exc_info=exc)
            return False
