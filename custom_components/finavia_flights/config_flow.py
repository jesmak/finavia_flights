"""Config flow.

The config entry holds the user's Finavia API key. Airports are config subentries, added and changed from the
integration page, so a second airport doesn't ask for the key again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, ConfigSubentryFlow, SubentryFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FinaviaAuthError, FinaviaClient, FinaviaError
from .const import (
    AIRPORTS,
    CONF_AIRPORT,
    CONF_DEPARTURES,
    CONF_DIRECTION,
    DEFAULT_DEPARTURES,
    DIRECTION_BOTH,
    DIRECTION_DEPARTURES,
    DIRECTION_SENSORS,
    DIRECTIONS,
    DOMAIN,
    KEY_CHECK_AIRPORT,
    MAX_DEPARTURES,
    PORTAL_URL,
    SUBENTRY_AIRPORT,
    airport_name,
    language_of,
)

KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})
PLACEHOLDERS = {"portal_url": PORTAL_URL}


async def check_api_key(hass: HomeAssistant, api_key: str) -> dict[str, str]:
    """Checks a key with Finavia by fetching a small airport's departures."""
    try:
        await FinaviaClient(async_get_clientsession(hass), api_key).flights_xml("dep", KEY_CHECK_AIRPORT)
    except FinaviaAuthError:
        return {CONF_API_KEY: "invalid_api_key"}
    except FinaviaError:
        return {"base": "cannot_connect"}
    return {}


class FinaviaFlightsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = str(user_input[CONF_API_KEY]).strip()
            errors = await check_api_key(self.hass, api_key)
            if not errors:
                return self.async_create_entry(title="Finavia", data={CONF_API_KEY: api_key})
        return self.async_show_form(step_id="user", data_schema=KEY_SCHEMA, errors=errors, description_placeholders=PLACEHOLDERS)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_new_key("reconfigure", self._get_reconfigure_entry(), "reconfigure_successful", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Asks for a new key when Finavia refuses the old one."""
        return await self._step_new_key("reauth_confirm", self._get_reauth_entry(), "reauth_successful", user_input)

    async def _step_new_key(self, step_id: str, entry: ConfigEntry, reason: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = str(user_input[CONF_API_KEY]).strip()
            errors = await check_api_key(self.hass, api_key)
            if not errors:
                # The update listener in __init__.py reloads the entry.
                self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_API_KEY: api_key})
                return self.async_abort(reason=reason)
        return self.async_show_form(step_id=step_id, data_schema=KEY_SCHEMA, errors=errors, description_placeholders=PLACEHOLDERS)

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_AIRPORT: AirportFlow}


def departures_field() -> dict[vol.Marker, Any]:
    return {
        vol.Required(CONF_DEPARTURES, default=DEFAULT_DEPARTURES): NumberSelector(
            NumberSelectorConfig(min=1, max=MAX_DEPARTURES, step=1, mode=NumberSelectorMode.BOX)
        )
    }


class AirportFlow(ConfigSubentryFlow):
    """Adding an airport's departures, arrivals or both (step "user"), and changing how many it lists (step "reconfigure").

    Each of an airport's directions can be added once.
    """

    def _added(self) -> dict[str, set[str]]:
        """The directions each airport has already, from the subentries as they are now."""
        added: dict[str, set[str]] = {}
        for subentry in self._get_entry().subentries.values():
            direction = str(subentry.data.get(CONF_DIRECTION, DIRECTION_DEPARTURES))
            added.setdefault(str(subentry.data.get(CONF_AIRPORT)), set()).update(DIRECTION_SENSORS[direction])
        return added

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        language = language_of(self.hass.config.language)
        errors: dict[str, str] = {}
        # Read again when the form is sent, as another window may have added the airport meanwhile.
        added = self._added()
        if user_input is not None:
            airport, direction = str(user_input[CONF_AIRPORT]), str(user_input[CONF_DIRECTION])
            if added.get(airport, set()) & set(DIRECTION_SENSORS[direction]):
                errors[CONF_DIRECTION] = "direction_added"
            else:
                return self.async_create_entry(
                    title=airport_name(airport, language),
                    data={CONF_AIRPORT: airport, CONF_DIRECTION: direction, CONF_DEPARTURES: int(user_input[CONF_DEPARTURES])},
                )

        both = set(DIRECTION_SENSORS[DIRECTION_BOTH])
        options = sorted(
            (
                SelectOptionDict(value=code, label=f"{airport_name(code, language)} ({code})")
                for code in AIRPORTS
                if not both <= added.get(code, set())
            ),
            key=lambda option: option["label"],
        )
        if not options:
            return self.async_abort(reason="all_added")
        schema = vol.Schema(
            {
                vol.Required(CONF_AIRPORT): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN, sort=False)
                ),
                vol.Required(CONF_DIRECTION, default=DIRECTION_BOTH): SelectSelector(
                    SelectSelectorConfig(options=DIRECTIONS, translation_key=CONF_DIRECTION, mode=SelectSelectorMode.LIST)
                ),
                **departures_field(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input or {}), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, data={**subentry.data, CONF_DEPARTURES: int(user_input[CONF_DEPARTURES])}
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(departures_field()), subentry.data),
            description_placeholders={"airport": subentry.title},
        )
