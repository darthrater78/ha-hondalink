from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DATA_RECALL_COORDINATOR, DOMAIN
from .entity import HondaLinkEntity
from .util import any_light_on, any_open_state, get_path, status_body


@dataclass(frozen=True, kw_only=True)
class HondaLinkBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


def _warning_lamp_on(body: dict[str, Any]) -> bool | None:
    """None when the vehicle reports no lamp data at all.

    Returning False there would show a green all-clear built on nothing.
    """
    messages = [
        message
        for group in get_path(body, "warningLamps.data", []) or []
        if isinstance(group, dict)
        for message in group.get("messages", []) or []
        if isinstance(message, dict)
    ]
    if not messages:
        return None
    return any(str(message.get("condition", "")).upper() == "ON" for message in messages)


# Observed on a MY23 vehicle: resStatus reads "IG RUN", not "ON". Anything
# unrecognised stays unknown rather than being asserted as off.
_ENGINE_OFF_STATES = {"OFF", "IG OFF", "IGOFF", "STOP", "STOPPED", "NO", "NONE"}
_ENGINE_ON_STATES = {"ON", "IG RUN", "IGRUN", "RUN", "RUNNING", "START", "STARTED"}


def _remote_engine_running(body: dict[str, Any]) -> bool | None:
    """None while the vehicle has not reported a usable remote start state."""
    status = get_path(body, "remoteEngineStart.vehicleStartEvent.resStatus")
    if status in (None, "", "unknown"):
        return None
    state = str(status).strip().upper()
    if state in _ENGINE_OFF_STATES:
        return False
    if state in _ENGINE_ON_STATES or "RUN" in state:
        return True
    return None


DOOR_KEYS = ["firstRowDriver", "firstRowPassenger", "secondRowDriver", "secondRowPassenger"]
WINDOW_KEYS = ["frontWindowDR", "frontWindowAS", "rearWindowRR", "rearWindowRL"]


BINARY_SENSORS: tuple[HondaLinkBinarySensorDescription, ...] = (
    HondaLinkBinarySensorDescription(
        key="any_door_open",
        translation_key="any_door_open",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda body: any_open_state(body, "doorStatus", DOOR_KEYS),
    ),
    HondaLinkBinarySensorDescription(
        key="hood_open",
        translation_key="hood_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda body: any_open_state(body, "doorStatus", ["hood"]),
    ),
    HondaLinkBinarySensorDescription(
        key="trunk_open",
        translation_key="trunk_open",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda body: any_open_state(body, "doorStatus", ["trunk"]),
    ),
    HondaLinkBinarySensorDescription(
        key="any_window_open",
        translation_key="any_window_open",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda body: any_open_state(body, "windowStatus", WINDOW_KEYS, "closeState"),
    ),
    HondaLinkBinarySensorDescription(
        key="any_light_on",
        translation_key="any_light_on",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=any_light_on,
    ),
    HondaLinkBinarySensorDescription(
        key="warning_lamp_on",
        translation_key="warning_lamp_on",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_warning_lamp_on,
    ),
    HondaLinkBinarySensorDescription(
        key="remote_engine_running",
        translation_key="remote_engine_running",
        value_fn=_remote_engine_running,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    entities: list[HondaLinkEntity] = [
        HondaLinkBinarySensor(coordinator, entry, description) for description in BINARY_SENSORS
    ]
    entities.append(HondaLinkRecallBinarySensor(data[DATA_RECALL_COORDINATOR], entry))
    async_add_entities(entities)


class HondaLinkBinarySensor(HondaLinkEntity, BinarySensorEntity):
    entity_description: HondaLinkBinarySensorDescription

    def __init__(self, coordinator, entry: ConfigEntry, description: HondaLinkBinarySensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(status_body(self.coordinator.data or {}))


def _recall_summary(recall: dict[str, Any]) -> dict[str, Any]:
    return {
        "campaign_number": recall.get("NHTSACampaignNumber"),
        "component": recall.get("Component"),
        "summary": recall.get("Summary"),
        "consequence": recall.get("Consequence"),
        "remedy": recall.get("Remedy"),
        "report_received_date": recall.get("ReportReceivedDate"),
        "manufacturer": recall.get("Manufacturer"),
        "park_it": recall.get("ParkIt"),
        "park_outside": recall.get("ParkOutSide"),
    }


class HondaLinkRecallBinarySensor(HondaLinkEntity, BinarySensorEntity):
    """On when NHTSA lists any open recall for this vehicle's make/model/year.

    NHTSA's recalls API is keyed by make/model/year, not VIN, so this can
    include recalls that do not apply to this specific VIN's build date or
    equipment. Check the campaign number against your vehicle before acting.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "active_recall")
        self._attr_translation_key = "active_recall"

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return len(self.coordinator.data) > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        recalls = self.coordinator.data or []
        return {
            "recall_count": len(recalls),
            "recalls": [_recall_summary(recall) for recall in recalls],
        }
