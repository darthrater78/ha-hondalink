from __future__ import annotations

import uuid

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession

from .api import HondaLinkAPI, HondaLinkAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_REG_KEY,
    CONF_COUNTRY,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_EXPIRES_AT,
    CONF_HIDAS_IDENT,
    CONF_LANGUAGE,
    CONF_LOCK_COMMAND,
    CONF_PASSWORD,
    CONF_PIN,
    CONF_REFRESH_TOKEN,
    CONF_SESSION_ID,
    CONF_UNLOCK_COMMAND,
    CONF_VIN,
    DATA_API,
    DATA_COORDINATOR,
    DATA_RECALL_COORDINATOR,
    DEFAULT_LOCK_COMMAND,
    DEFAULT_UNLOCK_COMMAND,
    DOMAIN,
)
from .coordinator import HondaLinkDataUpdateCoordinator, HondaLinkRecallCoordinator

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.LOCK,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    data = dict(entry.data)
    changed = False
    if not data.get(CONF_DEVICE_ID):
        data[CONF_DEVICE_ID] = str(uuid.uuid4())
        changed = True
    if not data.get(CONF_SESSION_ID):
        data[CONF_SESSION_ID] = str(uuid.uuid4())
        changed = True
    if changed:
        hass.config_entries.async_update_entry(entry, data=data)

    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    api = HondaLinkAPI(
        session,
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        pin=entry.options.get(CONF_PIN, data.get(CONF_PIN)),
        vin=data[CONF_VIN],
        client_reg_key=data.get(CONF_CLIENT_REG_KEY),
        access_token=data.get(CONF_ACCESS_TOKEN),
        refresh_token=data.get(CONF_REFRESH_TOKEN),
        expires_at=data.get(CONF_EXPIRES_AT),
        country=data.get(CONF_COUNTRY, "US"),
        language=data.get(CONF_LANGUAGE, "en"),
        hidas_ident=data.get(CONF_HIDAS_IDENT),
        device_id=data[CONF_DEVICE_ID],
        session_id=data[CONF_SESSION_ID],
        lock_command=entry.options.get(CONF_LOCK_COMMAND, DEFAULT_LOCK_COMMAND),
        unlock_command=entry.options.get(CONF_UNLOCK_COMMAND, DEFAULT_UNLOCK_COMMAND),
    )
    try:
        await api.async_ensure_login()
    except HondaLinkAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err

    auth_data = api.export_auth_data()
    if any(data.get(key) != value for key, value in auth_data.items()):
        hass.config_entries.async_update_entry(entry, data={**data, **auth_data})

    coordinator = HondaLinkDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    # Recalls come from NHTSA, not HondaLink, so a slow or unreachable NHTSA
    # API only leaves the recall entity unavailable rather than blocking setup.
    recall_coordinator = HondaLinkRecallCoordinator(hass, entry, async_get_clientsession(hass), data[CONF_VIN])
    await recall_coordinator.async_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_API: api,
        DATA_COORDINATOR: coordinator,
        DATA_RECALL_COORDINATOR: recall_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
