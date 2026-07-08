"""Config flow for VanMoof."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_KEY, CONF_USER_KEY_ID, DOMAIN, SX3_SERVICE_UUID


class VanMoofConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup of a VanMoof bike."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a bike found automatically.

        Only fires once a matcher is added to manifest.json (see README). The
        manual ``user`` step below works without it.
        """
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_credentials()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: pick a nearby connectable device, then enter keys."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_credentials()

        current = self._async_current_ids()
        bikes: dict[str, str] = {}
        others: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            label = f"{info.name or 'Unknown'} ({info.address})"
            if SX3_SERVICE_UUID in info.service_uuids:
                bikes[info.address] = f"{info.name or 'VanMoof'} ({info.address})"
            else:
                others[info.address] = label

        # Prefer the filtered VanMoof list. Only if nothing nearby advertises the
        # bike service do we fall back to every device (so the user is never
        # blocked, e.g. bike asleep / UUID not seen yet), plus a manual MAC field.
        if bikes:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(bikes)})
        elif others:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(others)})
        else:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): str})

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "found": "VanMoof bikes" if bikes else "no VanMoof detected"
            },
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the bike's encryption key and user key id."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or self._address or "VanMoof",
                data={
                    CONF_ADDRESS: self._address,
                    CONF_KEY: user_input[CONF_KEY],
                    CONF_USER_KEY_ID: user_input[CONF_USER_KEY_ID],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_KEY): str,
                vol.Required(CONF_USER_KEY_ID): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="credentials", data_schema=schema)
