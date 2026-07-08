"""Minimal async client for the VanMoof cloud account API.

Used by the config flow to fetch a bike's encryption key + user key id from the
owner's VanMoof account, so the user doesn't have to run a script by hand.

Only the read-only account endpoints are used. Runs on Home Assistant's shared
aiohttp session (no blocking I/O in the event loop).

Post-bankruptcy caveat: the my.vanmoof.com API changed hands (Lavoie) and may be
unreliable or disappear. Callers should handle VanMoofCloudError and fall back to
manual key entry / offline extraction (chwdt/vanmoof-tools).
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from aiohttp import ClientError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

API_URL = "https://my.vanmoof.com/api/v8"
# Shipped in the official VanMoof app; per pymoof it's the same for every user.
API_KEY = "fcb38d47-f14b-30cf-843b-26283f6a5819"

_TIMEOUT = 30


class VanMoofCloudError(Exception):
    """Cloud API unreachable or returned something unusable."""


class VanMoofAuthError(VanMoofCloudError):
    """Username/password rejected by the cloud API."""


async def async_get_bikes(
    hass: HomeAssistant, username: str, password: str
) -> list[dict[str, Any]]:
    """Log in and return the account's bikes (raw ``bikeDetails`` dicts).

    Each bike dict includes at least ``name``/``frameNumber`` and a ``key`` with
    ``encryptionKey`` + ``userKeyId``; ``macAddress`` when the API provides it.
    """
    session = async_get_clientsession(hass)
    basic = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")

    try:
        async with asyncio.timeout(_TIMEOUT):
            async with session.post(
                f"{API_URL}/authenticate",
                headers={"Api-Key": API_KEY, "Authorization": f"Basic {basic}"},
            ) as resp:
                auth = await resp.json(content_type=None)
    except (ClientError, TimeoutError) as err:
        raise VanMoofCloudError(f"authenticate request failed: {err}") from err
    except ValueError as err:
        raise VanMoofCloudError(f"authenticate returned non-JSON: {err}") from err

    token = auth.get("token") if isinstance(auth, dict) else None
    if not token:
        raise VanMoofAuthError(f"no token in response: {auth}")

    try:
        async with asyncio.timeout(_TIMEOUT):
            async with session.get(
                f"{API_URL}/getCustomerData",
                headers={"Api-Key": API_KEY, "Authorization": f"Bearer {token}"},
                params={"includeBikeDetails": ""},
            ) as resp:
                data = await resp.json(content_type=None)
    except (ClientError, TimeoutError) as err:
        raise VanMoofCloudError(f"getCustomerData request failed: {err}") from err
    except ValueError as err:
        raise VanMoofCloudError(f"getCustomerData returned non-JSON: {err}") from err

    bikes = (data.get("data") or {}).get("bikeDetails") if isinstance(data, dict) else None
    if not bikes:
        raise VanMoofCloudError(f"no bikes in account data: {data}")
    return bikes


def extract_mac(bike: dict[str, Any]) -> str | None:
    """Best-effort pull of the bike's BLE MAC from a bikeDetails dict."""
    for field in ("macAddress", "bleMacAddress", "mac"):
        value = bike.get(field)
        if value:
            return str(value).upper()
    return None


def bike_label(bike: dict[str, Any]) -> str:
    """Human label for a bike in the picker."""
    name = bike.get("name") or "VanMoof"
    frame = bike.get("frameNumber")
    return f"{name} ({frame})" if frame else name
