from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AudioflowUpdateCoordinator
from .const import DOMAIN, MANUFACTURER


class AudioflowEntity(CoordinatorEntity[AudioflowUpdateCoordinator]):
    def __init__(
        self, coordinator: AudioflowUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.config_entry = config_entry

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}-{type(self).__qualname__}"

    @property
    def device_info(self) -> DeviceInfo:
        state = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, state.switch.serial)},
            name=state.switch.name,
            model=state.switch.model,
            manufacturer=MANUFACTURER,
            sw_version=state.switch.version,
        )
