import typing

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AudioflowUpdateCoordinator
from .api import ZoneModel
from .const import DOMAIN
from .entity import AudioflowEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AudioflowUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ZoneEntity] = []
    for zone in coordinator.data.zones:
        entities.append(
            ZoneStateSwitch(
                coordinator=coordinator, config_entry=entry, zone_id=zone.zone_id
            )
        )
        entities.append(
            ZoneEnabledSwitch(
                coordinator=coordinator, config_entry=entry, zone_id=zone.zone_id
            )
        )

    async_add_entities(entities)


class ZoneEntity(AudioflowEntity):
    zone_id: int

    def __init__(
        self,
        *,
        coordinator: AudioflowUpdateCoordinator,
        config_entry: ConfigEntry,
        zone_id: int,
    ) -> None:
        super().__init__(coordinator, config_entry)
        self.zone_id = zone_id

    @property
    def zone(self) -> ZoneModel:
        state = self.coordinator.data
        zone = state.zone_by_id(self.zone_id)
        # this shouldn't be possible
        assert zone, "audioflow suddenly no longer has zone"
        return zone

    @property
    def unique_id(self) -> str:
        return f"{super().unique_id}-{self.zone_id}"

    @property
    def extra_state_attributes(self) -> dict[str, typing.Any]:
        parent_attributes = super().extra_state_attributes
        if parent_attributes is not None:
            attributes = dict(parent_attributes)
        else:
            attributes = {}
        attributes["zone_id"] = self.zone_id
        return attributes


class ZoneStateSwitch(ZoneEntity, SwitchEntity):
    async def async_turn_on(self, **kwargs: typing.Any) -> None:
        await self.coordinator.client.set_zone_state(self.zone_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: typing.Any) -> None:
        await self.coordinator.client.set_zone_state(self.zone_id, False)
        await self.coordinator.async_request_refresh()

    @property
    def name(self) -> str:
        return self.zone.name

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def available(self) -> bool:
        return self.zone.zone_enabled

    @property
    def icon(self) -> str:
        return "mdi:speaker"

    @property
    def is_on(self) -> bool:
        return self.zone.output_enabled


class ZoneEnabledSwitch(ZoneEntity, SwitchEntity):
    async def async_turn_on(self, **kwargs: typing.Any) -> None:
        await self.coordinator.client.set_zone_config(
            self.zone_id, enabled=True, zone_name=self.zone.name
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: typing.Any) -> None:
        await self.coordinator.client.set_zone_config(
            self.zone_id, enabled=False, zone_name=self.zone.name
        )
        await self.coordinator.async_request_refresh()

    @property
    def name(self) -> str:
        return f"{self.zone.name} Zone Enabled"

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def entity_category(self) -> EntityCategory:
        return EntityCategory.CONFIG

    @property
    def icon(self) -> str:
        return "mdi:export"

    @property
    def is_on(self) -> bool:
        return self.zone.zone_enabled
