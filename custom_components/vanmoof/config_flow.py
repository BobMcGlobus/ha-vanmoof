"""Config flow for VanMoof.

Two ways to set a bike up:

* **VanMoof account** (recommended): log in, pick the bike, and the encryption
  key + user key id are fetched automatically. If the account lists the bike's
  MAC we use it directly; otherwise we ask which nearby device it is.
* **Manual**: pick the nearby device, then paste the key + user key id (e.g. from
  offline extraction when the cloud is unavailable).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_KEY, CONF_USER_KEY_ID, DOMAIN, SX3_SERVICE_UUID
from .vanmoof_cloud import (
    VanMoofAuthError,
    VanMoofCloudError,
    async_get_bikes,
    bike_label,
    extract_mac,
)


class VanMoofConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup of a VanMoof bike."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._key: str | None = None
        self._user_key_id: int | None = None
        self._bikes: list[dict[str, Any]] = []
        # The account's macAddress is NOT the BLE advertising address, so it's
        # only used as a soft default in the picker, never as the real address.
        self._mac_hint: str | None = None

    # --- entry points --------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose the account or the manual path."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a bike found automatically via the manifest matcher."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        # Address is already known; still offer account vs. manual for the key.
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    # --- cloud path ----------------------------------------------------------

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Log in to the VanMoof account and fetch the bikes."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._bikes = await async_get_bikes(
                    self.hass,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except VanMoofAuthError:
                errors["base"] = "invalid_auth"
            except VanMoofCloudError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_cloud_pick()

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)

    async def async_step_cloud_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which account bike to add; key comes from the account."""
        if user_input is not None:
            bike = self._bikes[int(user_input["bike"])]
            key = bike.get("key") or {}
            self._key = key.get("encryptionKey")
            self._user_key_id = key.get("userKeyId")
            self._name = self._name or bike.get("name") or bike.get("frameNumber")

            # From discovery the address is the real advertised one -> use it.
            if self._address:
                await self.async_set_unique_id(
                    self._address, raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                return self._create_entry()
            # Otherwise DON'T trust the account MAC (it isn't the BLE address);
            # have the user pick the actually-advertising device. Keep the
            # account MAC only as a soft default hint.
            self._mac_hint = extract_mac(bike)
            return await self.async_step_pick_device()

        options = {str(i): bike_label(bike) for i, bike in enumerate(self._bikes)}
        schema = vol.Schema({vol.Required("bike"): vol.In(options)})
        return self.async_show_form(step_id="cloud_pick", data_schema=schema)

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fallback: choose the BLE device for an already-known cloud bike."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create_entry()

        return self.async_show_form(
            step_id="pick_device", data_schema=self._ble_picker_schema()
        )

    # --- manual path ---------------------------------------------------------

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the nearby device (unless discovery already gave us one)."""
        if self._address is not None:
            # Came from discovery: address known, go straight to key entry.
            return await self.async_step_credentials()

        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="manual", data_schema=self._ble_picker_schema()
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the bike's encryption key and user key id manually."""
        if user_input is not None:
            self._key = user_input[CONF_KEY]
            self._user_key_id = user_input[CONF_USER_KEY_ID]
            return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_KEY): str,
                vol.Required(CONF_USER_KEY_ID): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="credentials", data_schema=schema)

    # --- helpers -------------------------------------------------------------

    def _ble_picker_schema(self) -> vol.Schema:
        """Build a device picker, VanMoof bikes first, with sensible fallback."""
        current = self._async_current_ids()
        bikes: dict[str, str] = {}
        others: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            if SX3_SERVICE_UUID in info.service_uuids:
                bikes[info.address] = f"{info.name or 'VanMoof'} ({info.address})"
            else:
                others[info.address] = f"{info.name or 'Unknown'} ({info.address})"

        choices = bikes or others
        # Soft default: the account MAC, but only if it's actually advertising.
        # (It usually isn't the BLE address, so we never force it as a choice.)
        default = self._mac_hint if self._mac_hint in choices else None
        if choices:
            if default is not None:
                marker = vol.Required(CONF_ADDRESS, default=default)
            else:
                marker = vol.Required(CONF_ADDRESS)
            return vol.Schema({marker: vol.In(choices)})
        # Nothing advertising: the bike must be in range to be set up (the
        # account MAC won't connect). Offer a manual field as a last resort.
        return vol.Schema({vol.Required(CONF_ADDRESS): str})

    def _create_entry(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._name or self._address or "VanMoof",
            data={
                CONF_ADDRESS: self._address,
                CONF_KEY: self._key,
                CONF_USER_KEY_ID: self._user_key_id,
            },
        )
