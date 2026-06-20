# custom_components/pecron_local/config_flow.py
from __future__ import annotations

import asyncio
import base64
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .cloud_auth import CloudAuthError, cloud_login, fetch_auth_key, fetch_product_tsl, fetch_user_devices
from .const import (
    CONF_AUTH_KEY,
    CONF_DEVICE_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PREFERRED_TRANSPORT,
    CONF_PRODUCT_KEY,
    CONF_REGION,
    CONF_TSL,
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
        self._token: str = ""
        self._cloud_devices: list[dict] = []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            self._found_devices = await scan_for_devices()
            options: dict[str, str] = {}
            for device in self._found_devices:
                options[device["host"]] = f"{device['name']} ({device['host']})"
            options["manual_ip"] = "Enter IP address manually"
            options["manual_mac"] = "Enter Bluetooth MAC manually"
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required("device"): vol.In(options),
                }),
            )

        selection = user_input["device"]
        if selection == "manual_ip":
            return await self.async_step_manual_host()
        if selection == "manual_mac":
            return await self.async_step_manual_mac()
        # It's an IP from the LAN scan
        self._host = selection
        return await self.async_step_auth_method()

    async def async_step_manual_host(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="manual_host",
                data_schema=vol.Schema({vol.Required("host"): str}),
            )
        self._host = user_input["host"].strip()
        return await self.async_step_auth_method()

    async def async_step_manual_mac(self, user_input: dict | None = None) -> FlowResult:
        import re
        errors: dict[str, str] = {}
        if user_input is not None:
            mac = user_input["mac"].strip()
            if re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", mac):
                self._mac = mac
                return await self.async_step_auth_method()
            errors["mac"] = "invalid_mac"

        return self.async_show_form(
            step_id="manual_mac",
            data_schema=vol.Schema({vol.Required("mac"): str}),
            errors=errors,
        )

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
                self._token = token_data["token"]

                devices = await fetch_user_devices(self._token, self._region_key)
                if not devices:
                    errors["base"] = "no_devices_found"
                elif len(devices) == 1:
                    self._product_key = devices[0]["product_key"]
                    self._device_key = devices[0]["device_key"]
                    auth_key = await fetch_auth_key(
                        token=self._token,
                        region_key=self._region_key,
                        product_key=self._product_key,
                        device_key=self._device_key,
                    )
                    tsl = await fetch_product_tsl(self._token, self._region_key, self._product_key)
                    return self._create_entry(auth_key, tsl=tsl)
                else:
                    self._cloud_devices = devices
                    return await self.async_step_pick_cloud_device()
            except CloudAuthError as exc:
                _LOGGER.debug("Cloud auth error: %s", exc)
                errors["base"] = "login_failed"
            except Exception as exc:
                _LOGGER.exception("Unexpected error during cloud auth: %s", exc)
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

    async def async_step_pick_cloud_device(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            options = {
                d["device_key"]: f"{d['name']} ({d['device_key']})"
                for d in self._cloud_devices
            }
            return self.async_show_form(
                step_id="pick_cloud_device",
                data_schema=vol.Schema({
                    vol.Required("device_key"): vol.In(options),
                }),
            )

        device_key = user_input["device_key"]
        selected = next(d for d in self._cloud_devices if d["device_key"] == device_key)
        self._product_key = selected["product_key"]
        self._device_key = selected["device_key"]

        try:
            auth_key = await fetch_auth_key(
                token=self._token,
                region_key=self._region_key,
                product_key=self._product_key,
                device_key=self._device_key,
            )
            tsl = await fetch_product_tsl(self._token, self._region_key, self._product_key)
            return self._create_entry(auth_key, tsl=tsl)
        except CloudAuthError as exc:
            _LOGGER.debug("Failed to fetch auth key: %s", exc)
            return self.async_abort(reason="auth_key_fetch_failed")

    def _create_entry(self, auth_key: str, tsl: dict | None = None) -> FlowResult:
        preferred = TRANSPORT_TCP if self._host else TRANSPORT_BLE
        data: dict = {
            "host": self._host or None,
            CONF_MAC: self._mac or None,
            CONF_AUTH_KEY: auth_key,
            CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
            CONF_PREFERRED_TRANSPORT: preferred,
            CONF_DEVICE_KEY: self._device_key,
            CONF_PRODUCT_KEY: self._product_key,
            CONF_REGION: self._region_key,
        }
        if tsl:
            data[CONF_TSL] = tsl
        return self.async_create_entry(
            title=f"Pecron @ {self._host or self._mac}",
            data=data,
        )

    async def async_step_reconfigure(self, user_input: dict | None = None) -> FlowResult:
        """Re-authenticate with cloud to refresh the device TSL (data point IDs)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                token_data = await cloud_login(
                    user_input["email"], user_input["password"], user_input["region"]
                )
                token = token_data["token"]
                region_key = user_input["region"]
                product_key = self._get_reconfigure_entry().data.get(CONF_PRODUCT_KEY, "")
                if not product_key:
                    errors["base"] = "no_product_key"
                else:
                    tsl = await fetch_product_tsl(token, region_key, product_key)
                    if not tsl:
                        errors["base"] = "tsl_fetch_failed"
                    else:
                        return self.async_update_reload_and_abort(
                            self._get_reconfigure_entry(),
                            data_updates={CONF_TSL: tsl},
                            reason="reconfigure_successful",
                        )
            except CloudAuthError:
                errors["base"] = "login_failed"
            except Exception as exc:
                _LOGGER.exception("Reconfigure error: %s", exc)
                errors["base"] = "login_failed"

        stored_region = self._get_reconfigure_entry().data.get(CONF_REGION, "na")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required("email"): str,
                vol.Required("password"): str,
                vol.Required("region", default=stored_region): vol.In({
                    k: v["name"] for k, v in REGIONS.items()
                }),
            }),
            errors=errors,
        )
