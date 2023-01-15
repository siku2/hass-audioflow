from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AudioflowUpdateCoordinator
from .const import DOMAIN
from .entity import AudioflowEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AudioflowUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
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
    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def entity_category(self) -> EntityCategory:
        return EntityCategory.DIAGNOSTIC


class AfModel(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "Model"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch.model


class AfSerial(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "Serial"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch.serial


class AfVersion(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "Version"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.switch.version


class AfWifiSsid(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "WiFi SSID"

    @property
    def native_value(self) -> str | None:
        info = self.coordinator.data.switch.wifi_info()
        if not info:
            return None
        return info.ssid


class AfWifiChannel(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "WiFi Channel"

    @property
    def native_value(self) -> int | None:
        info = self.coordinator.data.switch.wifi_info()
        if not info:
            return None
        return info.channel


class AfWifiStrength(AudioflowSensorEntity):
    @property
    def name(self) -> str:
        return "WiFi Strength"

    @property
    def native_value(self) -> float | None:
        info = self.coordinator.data.switch.wifi_info()
        if not info:
            return None
        return info.strength

    @property
    def state_class(self) -> SensorStateClass:
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self) -> SensorDeviceClass:
        return SensorDeviceClass.SIGNAL_STRENGTH

    @property
    def native_unit_of_measurement(self) -> str:
        return "dBm"
