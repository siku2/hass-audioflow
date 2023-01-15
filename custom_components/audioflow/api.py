import asyncio
import dataclasses
import logging
import re

import aiohttp
import pydantic
import yarl

_LOGGER = logging.getLogger(__name__)


_WIFI_RE = re.compile(
    r"^(?P<ssid>.+) \[(?P<channel>[^]]+)\] \((?P<strength>[-\d]+)dbm\)$", re.IGNORECASE
)


@dataclasses.dataclass(kw_only=True)
class WifiInfo:
    ssid: str
    channel: int
    strength: float

    @classmethod
    def parse(cls, s: str):
        m = _WIFI_RE.fullmatch(s)
        if not m:
            raise ValueError("invalid format")

        return cls(
            ssid=m["ssid"], channel=int(m["channel"]), strength=float(m["strength"])
        )


_CACHED_WIFI_INFO_ATTR = "_cached_wifi_info"


class SwitchModel(pydantic.BaseModel):
    name: str
    model: str
    serial: str
    version: str
    wifi: str
    alexa: bool

    def parse_wifi_info(self) -> WifiInfo | None:
        try:
            return WifiInfo.parse(self.wifi)
        except Exception as exc:
            _LOGGER.warning("failed to parse wifi: %r", self.wifi, exc_info=exc)
            return None

    def wifi_info(self) -> WifiInfo | None:
        try:
            return self.__dict__[_CACHED_WIFI_INFO_ATTR]
        except KeyError:
            pass

        info = self.parse_wifi_info()
        self.__dict__[_CACHED_WIFI_INFO_ATTR] = info
        return info


class ZoneModel(pydantic.BaseModel):
    zone_id: int = pydantic.Field(alias="id")
    name: str
    zone_enabled: bool = pydantic.Field(alias="enabled")
    output_enabled: bool = pydantic.Field(alias="state")


@dataclasses.dataclass(kw_only=True)
class AudioflowDeviceState:
    switch: SwitchModel
    zones: list[ZoneModel]

    def zone_by_id(self, zone_id: int) -> ZoneModel | None:
        return next((zone for zone in self.zones if zone.zone_id == zone_id), None)


class _ZonesModel(pydantic.BaseModel):
    zones: list[ZoneModel]


class AudioflowDeviceClient:
    _session: aiohttp.ClientSession
    _base_url: yarl.URL
    _timeout: aiohttp.ClientTimeout

    def __init__(
        self, session: aiohttp.ClientSession, base_url: yarl.URL | str
    ) -> None:
        self._session = session
        self._base_url = yarl.URL(base_url)

        self._timeout = aiohttp.ClientTimeout(total=5.0)

    async def switch(self) -> SwitchModel:
        _LOGGER.debug("reading switch with base url: %s", self._base_url)
        async with self._session.get(
            self._base_url / "switch",
            timeout=self._timeout,
            raise_for_status=True,
        ) as resp:
            raw = await resp.json(content_type=None)
        return SwitchModel.parse_obj(raw)

    async def zones(self) -> list[ZoneModel]:
        _LOGGER.debug("reading zones with base url: %s", self._base_url)
        async with self._session.get(
            self._base_url / "zones",
            timeout=self._timeout,
            raise_for_status=True,
        ) as resp:
            raw = await resp.json(content_type=None)
        zones = _ZonesModel.parse_obj(raw).zones
        for zone in zones:
            # LOGIC: the API returns a zone 0 which is actually supposed to be zone 1 when used in the other APIs
            zone.zone_id += 1
        # make sure we're in ascending order
        zones.sort(key=lambda zone: zone.zone_id)
        return zones

    async def full_state(self) -> AudioflowDeviceState:
        switch, zones = await asyncio.gather(self.switch(), self.zones())
        return AudioflowDeviceState(switch=switch, zones=zones)

    async def _send_command(self, url: yarl.URL, data: str) -> None:
        async with self._session.put(
            url,
            data=data,
            headers={"Content-Type": "text/plain"},
            timeout=self._timeout,
            raise_for_status=True,
        ):
            pass

    async def set_zone_state(self, zone_id: int, is_on: bool) -> None:
        _LOGGER.debug(
            "setting zone %s state to %s with base url: %s",
            zone_id,
            is_on,
            self._base_url,
        )
        await self._send_command(
            self._base_url / "zones" / str(zone_id), "1" if is_on else "0"
        )

    async def set_zone_config(
        self, zone_id: int, *, enabled: bool, zone_name: str
    ) -> None:
        _LOGGER.debug(
            "setting zone %s config { name: %r, enabled: %r } with base url: %s",
            zone_id,
            zone_name,
            enabled,
            self._base_url,
        )
        await self._send_command(
            self._base_url / "zonename" / str(zone_id),
            ("1" if enabled else "0") + zone_name.strip(),
        )
