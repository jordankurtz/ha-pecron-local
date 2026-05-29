# custom_components/pecron_local/config_flow.py
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .cloud_auth import CloudAuthError, cloud_login, fetch_auth_key
from .const import (
    BLE_DEVICE_PREFIX,
    CONF_AUTH_KEY,
    CONF_DEVICE_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PREFERRED_TRANSPORT,
    CONF_PRODUCT_KEY,
    CONF_REGION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    REGIONS,
    TRANSPORT_BLE,
    TRANSPORT_TCP,
)

_LOGGER = logging.getLogger(__name__)


async def scan_for_devices(timeout: float = 5.0) -> list[dict]:
    """Probe LAN on port 6607 to find Pecron devices. Returns [{host, name}]."""
    import socket
    import ipaddress

    results = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        return results

    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)

    async def probe(ip: str) -> str | None:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, DEFAULT_PORT), timeout=0.5
            )
            writer.close()
            await writer.wait_closed()
            return ip
        except Exception:
            return None

    tasks = [probe(str(host)) for host in list(network.hosts())[:254]]
    found = await asyncio.gather(*tasks)
    for ip in found:
        if ip:
            results.append({"host": ip, "name": f"Pecron @ {ip}"})
    return results


class PecronLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str = ""
        self._mac: str = ""
        self._device_key: str = ""
        self._product_key: str = ""
        self._region_key: str = "na"
        self._found_devices: list[dict] = []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            self._found_devices = await scan_for_devices()
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Optional("host", default=""): str,
                    vol.Optional("mac", default=""): str,
                }),
                description_placeholders={
                    "found": ", ".join(d["host"] for d in self._found_devices) or "none found"
                },
            )

        self._host = user_input.get("host", "").strip()
        self._mac = user_input.get("mac", "").strip()
        return await self.async_step_auth_method()

    async def async_step_bluetooth(self, discovery_info) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._mac = discovery_info.address
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_auth_method()

    async def async_step_auth_method(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="auth_method",
                data_schema=vol.Schema({
                    vol.Required("auth_method"): vol.In({
                        "credentials": "Sign in with Pecron account",
                        "manual": "Enter auth key manually",
                    }),
                }),
            )
        if user_input["auth_method"] == "manual":
            return await self.async_step_manual_key()
        return await self.async_step_credentials()

    async def async_step_manual_key(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            auth_key = user_input.get("auth_key", "").strip()
            try:
                base64.b64decode(auth_key)
            except Exception:
                errors["auth_key"] = "invalid_auth_key"
            else:
                return self._create_entry(auth_key)

        return self.async_show_form(
            step_id="manual_key",
            data_schema=vol.Schema({vol.Required("auth_key"): str}),
            errors=errors,
        )

    async def async_step_credentials(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token_data = await cloud_login(
                    user_input["email"], user_input["password"], user_input["region"]
                )
                self._region_key = user_input["region"]
                auth_key = await fetch_auth_key(
                    token=token_data["token"],
                    region_key=self._region_key,
                    product_key=self._product_key or "",
                    device_key=self._device_key or self._mac.replace(":", ""),
                )
                return self._create_entry(auth_key)
            except CloudAuthError as exc:
                _LOGGER.debug("Cloud auth error: %s", exc)
                errors["base"] = "login_failed"

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema({
                vol.Required("email"): str,
                vol.Required("password"): str,
                vol.Required("region", default="na"): vol.In({
                    k: v["name"] for k, v in REGIONS.items()
                }),
            }),
            errors=errors,
        )

    def _create_entry(self, auth_key: str) -> FlowResult:
        preferred = TRANSPORT_TCP if self._host else TRANSPORT_BLE
        return self.async_create_entry(
            title=f"Pecron @ {self._host or self._mac}",
            data={
                "host": self._host or None,
                CONF_MAC: self._mac or None,
                CONF_AUTH_KEY: auth_key,
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                CONF_PREFERRED_TRANSPORT: preferred,
                CONF_DEVICE_KEY: self._device_key,
                CONF_PRODUCT_KEY: self._product_key,
                CONF_REGION: self._region_key,
            },
        )
