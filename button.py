from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DATA_RECALL_COORDINATOR, DOMAIN
from .coordinator import HondaLinkDataUpdateCoordinator
from .entity import HondaLinkEntity


@dataclass(frozen=True, kw_only=True)
class HondaLinkButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[HondaLinkDataUpdateCoordinator], object]


BUTTONS: tuple[HondaLinkButtonDescription, ...] = (
    HondaLinkButtonDescription(
        key="start_engine",
        translation_key="start_engine",
        icon="mdi:engine",
        press_fn=lambda coordinator: coordinator.async_start_engine(),
    ),
    HondaLinkButtonDescription(
        key="stop_engine",
        translation_key="stop_engine",
        icon="mdi:engine-off",
        press_fn=lambda coordinator: coordinator.async_stop_engine(),
    ),
    HondaLinkButtonDescription(
        key="horn",
        translation_key="horn",
        icon="mdi:bullhorn",
        press_fn=lambda coordinator: coordinator.async_horn(),
    ),
    HondaLinkButtonDescription(
        key="lights",
        translation_key="lights",
        icon="mdi:car-light-high",
        press_fn=lambda coordinator: coordinator.async_lights(),
    ),
    HondaLinkButtonDescription(
        key="stop_horn_lights",
        translation_key="stop_horn_lights",
        icon="mdi:car-light-alert",
        press_fn=lambda coordinator: coordinator.async_stop_horn_lights(),
    ),
    HondaLinkButtonDescription(
        key="refresh",
        translation_key="refresh",
        icon="mdi:refresh",
        press_fn=lambda coordinator: coordinator.async_force_refresh(),
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data[DATA_COORDINATOR]
    entities: list[HondaLinkEntity] = [
        HondaLinkButton(coordinator, entry, description) for description in BUTTONS
    ]
    entities.append(HondaLinkRecallCheckButton(data[DATA_RECALL_COORDINATOR], entry))
    async_add_entities(entities)


class HondaLinkButton(HondaLinkEntity, ButtonEntity):
    entity_description: HondaLinkButtonDescription

    def __init__(self, coordinator: HondaLinkDataUpdateCoordinator, entry: ConfigEntry, description: HondaLinkButtonDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)


class HondaLinkRecallCheckButton(HondaLinkEntity, ButtonEntity):
    _attr_icon = "mdi:car-wrench"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "check_recalls")
        self._attr_translation_key = "check_recalls"

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
