from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DIAGNOSTIC_ATTRIBUTES,
    DATA_COORDINATOR,
    DEFAULT_DIAGNOSTIC_ATTRIBUTES,
    DOMAIN,
)
from .entity import HondaLinkEntity
from .util import (
    find_12v_battery_candidates,
    find_12v_battery_status,
    get_path,
    leaf_paths,
    parse_iso_datetime,
    status_body,
    to_float,
    to_int,
)


UNIT_MAP: dict[str, str] = {
    "kpa": UnitOfPressure.KPA,
    "psi": UnitOfPressure.PSI,
    "bar": UnitOfPressure.BAR,
    "miles": UnitOfLength.MILES,
    "mile": UnitOfLength.MILES,
    "mi": UnitOfLength.MILES,
    "km": UnitOfLength.KILOMETERS,
    "kilometers": UnitOfLength.KILOMETERS,
    "kilometres": UnitOfLength.KILOMETERS,
    "mph": UnitOfSpeed.MILES_PER_HOUR,
    "kph": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "km/h": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "%": PERCENTAGE,
}


@dataclass(frozen=True, kw_only=True)
class HondaLinkSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    # Payload path holding the unit Honda reports for this value, if any.
    unit_path: str | None = None


def _tire(path: str):
    return lambda body: to_int(get_path(body, f"tireStatus.{path}.pressureData.value"))


SENSORS: tuple[HondaLinkSensorDescription, ...] = (
    HondaLinkSensorDescription(
        key="fuel_level",
        translation_key="fuel_level",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:gas-station",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda body: to_int(get_path(body, "fuelLevel.currentLevel.value")),
    ),
    HondaLinkSensorDescription(
        key="range",
        translation_key="range",
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="fuelLevel.driveRange.unit",
        value_fn=lambda body: to_int(get_path(body, "fuelLevel.driveRange.value")),
    ),
    HondaLinkSensorDescription(
        key="odometer",
        translation_key="odometer",
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        unit_path="odometer.unit",
        value_fn=lambda body: to_int(get_path(body, "odometer.value")),
    ),
    HondaLinkSensorDescription(
        key="oil_life",
        translation_key="oil_life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda body: to_int(get_path(body, "oilLife.value")),
    ),
    HondaLinkSensorDescription(
        key="12v_battery_status",
        translation_key="12v_battery_status",
        value_fn=find_12v_battery_status,
        attr_fn=lambda body: {
            "battery_candidates": find_12v_battery_candidates(body),
            "dashboard_keys": sorted(body.keys()),
            "dashboard_leaf_paths": leaf_paths(body),
        },
    ),
    HondaLinkSensorDescription(
        key="front_left_tire_pressure",
        translation_key="front_left_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="tireStatus.frontLeft.pressureData.unit",
        value_fn=_tire("frontLeft"),
    ),
    HondaLinkSensorDescription(
        key="front_right_tire_pressure",
        translation_key="front_right_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="tireStatus.frontRight.pressureData.unit",
        value_fn=_tire("frontRight"),
    ),
    HondaLinkSensorDescription(
        key="rear_left_tire_pressure",
        translation_key="rear_left_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="tireStatus.rearLeft.pressureData.unit",
        value_fn=_tire("rearLeft"),
    ),
    HondaLinkSensorDescription(
        key="rear_right_tire_pressure",
        translation_key="rear_right_tire_pressure",
        native_unit_of_measurement=UnitOfPressure.KPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="tireStatus.rearRight.pressureData.unit",
        value_fn=_tire("rearRight"),
    ),
    HondaLinkSensorDescription(
        key="vehicle_speed",
        translation_key="vehicle_speed",
        native_unit_of_measurement=UnitOfSpeed.MILES_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        unit_path="gpsData.velocity.unit",
        value_fn=lambda body: to_float(get_path(body, "gpsData.velocity.value")),
    ),
    HondaLinkSensorDescription(
        key="remote_engine_status",
        translation_key="remote_engine_status",
        value_fn=lambda body: get_path(body, "remoteEngineStart.vehicleStartEvent.resStatus"),
    ),
    HondaLinkSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda body: parse_iso_datetime(get_path(body, "timestamp")),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(HondaLinkSensor(coordinator, entry, description) for description in SENSORS)


class HondaLinkSensor(HondaLinkEntity, SensorEntity):
    entity_description: HondaLinkSensorDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: HondaLinkSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(status_body(self.coordinator.data or {}))

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Prefer the unit Honda reports, falling back to the declared default."""
        unit_path = self.entity_description.unit_path
        if unit_path:
            reported = get_path(status_body(self.coordinator.data or {}), unit_path)
            mapped = UNIT_MAP.get(str(reported).strip().lower())
            if mapped:
                return mapped
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        # Off by default: these attributes run to hundreds of values and are
        # written to the recorder database on every poll. Enable in the
        # integration options only while mapping a new vehicle.
        if not self.entry.options.get(CONF_DIAGNOSTIC_ATTRIBUTES, DEFAULT_DIAGNOSTIC_ATTRIBUTES):
            return None
        return self.entity_description.attr_fn(status_body(self.coordinator.data or {}))
