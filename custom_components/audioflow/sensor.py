from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Coordinator
from .const import DOMAIN
from .entity import AudioflowEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: Coordinator = hass.data[DOMAIN][entry.entry_id]
    entity_classes = [
        AfModel,
        AfSerial,
        AfVersion,
        AfWifiSsid,
        AfWifiChannel,
        AfWifiStrength,
    ]
    async_add_entities(
        [
            entity_cls(coordinator=coordinator, config_entry=entry)
            for entity_cls in entity_classes
        ]
    )


class AudioflowSensorEntity(AudioflowEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC


class AfModel(AudioflowSensorEntity):
    _attr_translation_key = "model"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch["model"]


class AfSerial(AudioflowSensorEntity):
    _attr_translation_key = "serial"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch["serial"]


class AfVersion(AudioflowSensorEntity):
    _attr_translation_key = "version"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch["version"]


class AfWifiSsid(AudioflowSensorEntity):
    _attr_translation_key = "wifi_ssid"
    _attr_icon = "mdi:wifi"

    @property
    def native_value(self) -> str | None:
        info = self.coordinator.data.wifi
        if not info:
            return None
        return info.ssid


class AfWifiChannel(AudioflowSensorEntity):
    _attr_translation_key = "wifi_channel"
    _attr_icon = "mdi:wifi"

    @property
    def native_value(self) -> int | None:
        info = self.coordinator.data.wifi
        if not info:
            return None
        return info.channel


class AfWifiStrength(AudioflowSensorEntity):
    _attr_translation_key = "wifi_strength"

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        info = self.coordinator.data.wifi
        if not info:
            return None
        return info.strength
