from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Coordinator


class AudioflowEntity(CoordinatorEntity[Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Coordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator)

        self._attr_unique_id = f"{config_entry.entry_id}-{type(self).__qualname__}"
        self._attr_device_info = coordinator.device_info
