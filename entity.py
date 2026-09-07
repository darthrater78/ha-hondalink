from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import CONF_VEHICLE_INFO, CONF_VIN, DOMAIN


class HondaLinkEntity(CoordinatorEntity[DataUpdateCoordinator]):
    """Base entity for anything identified by VIN and shown on the vehicle device.

    Not typed to a specific coordinator: it backs entities driven by the
    HondaLink telematics coordinator as well as the independent NHTSA recall
    coordinator, and only needs coordinator.data plumbing from the base class.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.vin = entry.data[CONF_VIN]
        self._attr_unique_id = f"{self.vin}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        vehicle = self.entry.data.get(CONF_VEHICLE_INFO) or {}
        year = vehicle.get("ModelYear")
        model = vehicle.get("ModelGroupNameFriendly") or vehicle.get("ModelCode")
        trim = vehicle.get("ModelTrimTypeCode")
        model_name = " ".join(str(x) for x in (year, model, trim) if x)
        return DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer=vehicle.get("DivisionName") or "Honda",
            model=model_name or None,
            name=vehicle.get("Alias Name") or model_name or f"Honda {self.vin[-6:]}",
            serial_number=self.vin,
            configuration_url="https://mygarage.honda.com/",
        )
