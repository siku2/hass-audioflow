from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Coordinator
from .api import Zone
from .const import DOMAIN
from .entity import AudioflowEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []
    for zone in coordinator.data.zones:
        entities.append(
            ZoneStateSwitch(
                coordinator=coordinator, config_entry=entry, zone_id=zone["id"]
            )
        )
        entities.append(
            ZoneEnabledSwitch(
                coordinator=coordinator, config_entry=entry, zone_id=zone["id"]
            )
        )

    async_add_entities(entities)


class ZoneEntity(AudioflowEntity):
    zone_id: int

    def __init__(
        self,
        *,
        coordinator: Coordinator,
        config_entry: ConfigEntry,
        zone_id: int,
    ) -> None:
        super().__init__(coordinator, config_entry)
        self.zone_id = zone_id

        self._attr_unique_id = f"{super().unique_id}-{self.zone_id}"

    @property
    def af_zone(self) -> Zone:
        state = self.coordinator.data
        zone = state.zone_by_id(self.zone_id)
        # this shouldn't be possible
        assert zone, "audioflow suddenly no longer has zone"
        return zone


class ZoneStateSwitch(ZoneEntity, SwitchEntity):
    _attr_icon = "mdi:speaker"

    def __init__(
        self, *, coordinator: Coordinator, config_entry: ConfigEntry, zone_id: int
    ) -> None:
        super().__init__(
            coordinator=coordinator, config_entry=config_entry, zone_id=zone_id
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_state(self.zone_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_state(self.zone_id, False)
        await self.coordinator.async_request_refresh()

    @property
    def name(self) -> str:
        return self.af_zone["name"]

    @property
    def available(self) -> bool:
        return bool(self.af_zone["enabled"])

    @property
    def is_on(self) -> bool:
        return self.af_zone["state"] == "on"


class ZoneEnabledSwitch(ZoneEntity, SwitchEntity):
    _attr_icon = "mdi:export"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "enabled"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_config(
            self.zone_id, enabled=True, zone_name=self.af_zone["name"]
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_config(
            self.zone_id, enabled=False, zone_name=self.af_zone["name"]
        )
        await self.coordinator.async_request_refresh()

    @property
    def name(self) -> str | None:
        if (name_translation_key := self._name_translation_key) and (
            name_template := self.platform.platform_translations.get(
                name_translation_key
            )
        ):
            return name_template.format(name=self.af_zone["name"])
        return None

    @property
    def is_on(self) -> bool:
        return bool(self.af_zone["enabled"])
