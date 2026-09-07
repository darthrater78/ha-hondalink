from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    HondaLinkAPI,
    HondaLinkAuthError,
    HondaLinkCommandError,
    HondaLinkCommandResult,
    HondaLinkError,
)
from .const import CONF_SCAN_INTERVAL, CONF_VIN, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HondaLinkDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: HondaLinkAPI) -> None:
        self.api = api
        self.vin = entry.data[CONF_VIN]
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            logging.getLogger(__name__),
            config_entry=entry,
            name=f"{DOMAIN}-{self.vin}",
            update_interval=timedelta(minutes=interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_dashboard_latest(self.vin)
        except HondaLinkAuthError as err:
            # Must precede HondaLinkError: bad credentials are permanent until the
            # user re-enters them, so retrying on a poll loop only risks lockout.
            raise ConfigEntryAuthFailed(str(err)) from err
        except HondaLinkError as err:
            raise UpdateFailed(str(err)) from err

    async def async_force_refresh(self) -> None:
        try:
            result = await self.api.async_request_dashboard_update(self.vin)
        except HondaLinkError as err:
            _LOGGER.warning("HondaLink live dashboard refresh request failed: %s", err)
            await self.async_refresh()
            return
        self._schedule_completion(result, "dashboard refresh")

    async def async_start_engine(self) -> None:
        await self._run_command(self.api.async_start_engine)

    async def async_stop_engine(self) -> None:
        await self._run_command(self.api.async_stop_engine)

    async def async_lock(self) -> None:
        await self._run_command(self.api.async_lock)

    async def async_unlock(self) -> None:
        await self._run_command(self.api.async_unlock)

    async def async_horn(self) -> None:
        await self._run_command(self.api.async_horn)

    async def async_lights(self) -> None:
        await self._run_command(self.api.async_lights)

    async def async_stop_horn_lights(self) -> None:
        await self._run_command(self.api.async_stop_horn_lights)

    async def _run_command(self, command) -> None:
        """Send a command and return once the vehicle has accepted it.

        Rejections (bad PIN, unsupported command) surface here and reach the user.
        Carrying the command out can take over a minute, which is too long to hold
        a service call open, so completion is awaited in the background and the
        coordinator refreshed once the vehicle reports back.
        """
        try:
            result = await command()
        except HondaLinkCommandError as err:
            raise HomeAssistantError(str(err)) from err
        self._schedule_completion(result, "command")

    def _schedule_completion(self, result: HondaLinkCommandResult, label: str) -> None:
        if not result.request_id:
            self.hass.async_create_task(self.async_request_refresh())
            return
        self.config_entry.async_create_background_task(
            self.hass,
            self._await_completion(result, label),
            name=f"{DOMAIN} {self.vin} {label}",
            eager_start=True,
        )

    async def _await_completion(self, result: HondaLinkCommandResult, label: str) -> None:
        try:
            await self.api.async_await_command(result)
        except HondaLinkError as err:
            # The user already got acceptance; a later failure is only logged.
            _LOGGER.warning("HondaLink %s did not complete: %s", label, err)
        await self.async_refresh()
