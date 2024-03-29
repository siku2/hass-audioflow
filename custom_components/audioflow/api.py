import asyncio
import dataclasses
import logging
import re
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from ipaddress import IPv4Interface
from types import TracebackType
from typing import Any, Literal, TypedDict

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)


_WIFI_RE = re.compile(
    r"^(?P<ssid>.+) \[(?P<channel>[^]]+)\] \((?P<strength>[-\d]+)dbm\)$", re.IGNORECASE
)


@dataclasses.dataclass(slots=True, kw_only=True)
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


class Switch(TypedDict, total=True):
    name: str
    model: str
    serial: str
    version: str
    wifi: str
    alexa: bool


class Zone(TypedDict, total=True):
    id: int
    name: str
    enabled: int
    state: Literal["on"] | Literal["off"]


@dataclasses.dataclass(slots=True, kw_only=True)
class FullState:
    switch: Switch
    zones: list[Zone]
    wifi: WifiInfo | None

    def zone_by_id(self, zone_id: int) -> Zone | None:
        return next((zone for zone in self.zones if zone["id"] == zone_id), None)


class _ZonesResponse(TypedDict):
    zones: list[Zone]


class Client:
    _session: aiohttp.ClientSession
    _base_url: URL
    _timeout: aiohttp.ClientTimeout

    def __init__(self, session: aiohttp.ClientSession, base_url: URL | str) -> None:
        self._session = session
        self._base_url = URL(base_url)

        self._timeout = aiohttp.ClientTimeout(total=5.0)

    async def _request(self, method: Literal["GET"], path: str) -> Any:
        _LOGGER.debug("performing %s on %s", method, path)
        async with self._session.get(
            self._base_url / path,
            timeout=self._timeout,
            raise_for_status=True,
        ) as resp:
            data = await resp.json(content_type=None)
        _LOGGER.debug("response: %s", data)
        return data

    async def switch(self) -> Switch:
        _LOGGER.debug("reading switch with base url: %s", self._base_url)
        return await self._request("GET", "switch")

    async def zones(self) -> list[Zone]:
        _LOGGER.debug("reading zones with base url: %s", self._base_url)
        raw: _ZonesResponse = await self._request("GET", "zones")
        zones = raw["zones"]
        # fix the broken zone id assignment.
        # ids returned by this API start from 0, but the other APIs expect the id to be 1-based
        for zone_id, zone in enumerate(zones, 1):
            zone["id"] = zone_id
        return zones

    async def full_state(self) -> FullState:
        switch, zones = await asyncio.gather(self.switch(), self.zones())
        try:
            wifi = WifiInfo.parse(switch["wifi"])
        except ValueError:
            _LOGGER.warn(f"failed to parse wifi info {switch['wifi']!r}")
            wifi = None
        return FullState(switch=switch, zones=zones, wifi=wifi)

    async def _send_command(self, path: str, data: str) -> None:
        async with self._session.put(
            self._base_url / path,
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
        await self._send_command(f"zones/{zone_id}", "1" if is_on else "0")

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
            f"zonename/{zone_id}",
            ("1" if enabled else "0") + zone_name.strip(),
        )


@dataclasses.dataclass(slots=True, kw_only=True)
class DiscoveryInfo:
    host: str
    model: str
    serial_number: str


def discover(
    interface: IPv4Interface,
    timeout: float | None = None,
) -> AbstractAsyncContextManager[AsyncIterator[DiscoveryInfo]]:
    return _DiscoveryContextManager(interface, timeout)


async def discover_list(
    interface: IPv4Interface, timeout: float
) -> list[DiscoveryInfo]:
    collected: list[DiscoveryInfo] = []
    async with discover(interface, timeout) as discoverer:
        async for discovery in discoverer:
            collected.append(discovery)
    return collected


_DISCOVERY_PING = b"afping"
_DISCOVERY_PONG = b"afpong"
_DISCOVERY_MODEL_BYTES = 8
_DISCOVERY_PORT = 10499


def _cstr(b: bytes) -> str:
    return b.split(b"\x00", 1)[0].decode("ascii")


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.discoveries: asyncio.Queue[DiscoveryInfo | None] = asyncio.Queue()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        _LOGGER.debug("connection made")

    def connection_lost(self, exc: Exception | None) -> None:
        _LOGGER.debug("connection lost: %s", exc)
        self.discoveries.put_nowait(None)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        if not data.startswith(_DISCOVERY_PONG):
            return

        _LOGGER.debug("received afpong from %s: %s", addr, data)

        model_start = len(_DISCOVERY_PONG)
        serial_start = model_start + _DISCOVERY_MODEL_BYTES
        try:
            info = DiscoveryInfo(
                host=str(addr[0]),
                model=_cstr(data[model_start:serial_start]),
                serial_number=_cstr(data[serial_start:]),
            )
        except IndexError:
            _LOGGER.exception("failed to parse afpong")
            return

        self.discoveries.put_nowait(info)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warn("received error", exc_info=exc)


class _DiscoveryContextManager(
    AbstractAsyncContextManager[AsyncIterator[DiscoveryInfo]]
):
    def __init__(self, interface: IPv4Interface, timeout: float | None) -> None:
        self.interface = interface
        self.timeout = timeout
        self._transport: asyncio.DatagramTransport | None = None

    async def _make_iter(
        self, protocol: _DiscoveryProtocol
    ) -> AsyncIterator[DiscoveryInfo]:
        while True:
            discovery = await protocol.discoveries.get()
            if discovery is None:
                break
            yield discovery

    async def __aenter__(self) -> AsyncIterator[DiscoveryInfo]:
        loop = asyncio.get_running_loop()
        self._transport, protocol = await loop.create_datagram_endpoint(
            _DiscoveryProtocol,
            local_addr=(str(self.interface.ip), _DISCOVERY_PORT),
            allow_broadcast=True,
        )
        self._transport.sendto(
            _DISCOVERY_PING,
            (str(self.interface.network.broadcast_address), _DISCOVERY_PORT),
        )

        if self.timeout:
            loop.call_later(self.timeout, self._on_timeout)

        return self._make_iter(protocol)

    def _on_timeout(self) -> None:
        if self._transport:
            self._transport.close()

    async def __aexit__(
        self,
        __exc_type: type[BaseException] | None,
        __exc_value: BaseException | None,
        __traceback: TracebackType | None,
    ) -> bool | None:
        if self._transport:
            self._transport.abort()
        return None
