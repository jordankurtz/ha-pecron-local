"""One-time cloud auth key fetch from Pecron/Quectel backend.

Ported from https://github.com/attractify-logan/pecron-monitor (MIT License).
Called only during config flow setup. No ongoing cloud dependency.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import string

import aiohttp

from .const import REGIONS


class CloudAuthError(Exception):
    """Raised when cloud authentication fails."""


def _make_auth_params(email: str, password: str, region: dict) -> dict:
    """Build encrypted login params (matches Pecron app protocol)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as sym_padding

    rand = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    md5 = hashlib.md5(rand.encode()).hexdigest().upper()
    aes_key = md5[8:24].encode()
    iv = (md5[8:24][8:16] + md5[8:24][0:8]).encode()

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(password.encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    enc = cipher.encryptor()
    enc_pwd = base64.b64encode(enc.update(padded) + enc.finalize()).decode()

    sig_input = email + enc_pwd + rand + region["user_domain_secret"]
    signature = hashlib.sha256(sig_input.encode()).hexdigest()
    return {
        "email": email,
        "pwd": enc_pwd,
        "random": rand,
        "userDomain": region["user_domain"],
        "signature": signature,
    }


async def _do_login(session: aiohttp.ClientSession, email: str, password: str, region: dict) -> dict:
    params = _make_auth_params(email, password, region)
    url = region["base_url"] + "/v2/enduser/enduserapi/emailPwdLogin"
    async with session.post(url, data=params) as resp:
        body = await resp.json()

    if body.get("code") != 200:
        raise CloudAuthError(f"Login failed (code {body.get('code')}): {body.get('msg', body)}")

    token = body["data"]["accessToken"]["token"]
    jwt_parts = token.split(".")
    payload_b64 = jwt_parts[1] + "=" * (4 - len(jwt_parts[1]) % 4)
    jwt_payload = json.loads(base64.b64decode(payload_b64))
    return {"token": token, "uid": jwt_payload["uid"]}


_DOMAIN_RETRY_CODES = {5015, 5031, 5420}


async def cloud_login(email: str, password: str, region_key: str) -> dict:
    """Log in and return {'token': ..., 'uid': ...}. Raises CloudAuthError on failure."""
    region = REGIONS[region_key]
    async with aiohttp.ClientSession() as session:
        try:
            return await _do_login(session, email, password, region)
        except CloudAuthError as primary_err:
            fallback_domain = region.get("user_domain_fallback")
            fallback_secret = region.get("user_domain_secret_fallback")
            if not fallback_domain or not fallback_secret:
                raise
            err = str(primary_err)
            if not any(f"code {c}" in err for c in _DOMAIN_RETRY_CODES):
                raise
            fallback_region = {**region, "user_domain": fallback_domain, "user_domain_secret": fallback_secret}
            return await _do_login(session, email, password, fallback_region)


async def fetch_user_devices(token: str, region_key: str) -> list[dict]:
    """Fetch all devices bound to the user's account.

    Returns list of {name, product_key, device_key}.
    Ported from pecron-monitor cloud_api.get_user_devices (MIT License).
    """
    region = REGIONS[region_key]
    async with aiohttp.ClientSession() as session:
        url = region["base_url"] + "/v2/binding/enduserapi/userDeviceList"
        async with session.get(url, headers={"Authorization": token}) as resp:
            body = await resp.json(content_type=None)
    if body.get("code") != 200:
        return []
    data = body.get("data", {})
    device_list = data.get("list", data) if isinstance(data, dict) else data
    if not isinstance(device_list, list):
        return []
    devices = []
    for d in device_list:
        pk = d.get("productKey", "")
        dk = d.get("deviceKey", "")
        name = d.get("productName", d.get("deviceName", "Unknown"))
        if pk and dk:
            devices.append({"product_key": pk, "device_key": dk, "name": name})
    return devices


async def fetch_auth_key(token: str, region_key: str, product_key: str, device_key: str) -> str:
    """Fetch device AES auth key from cloud. Returns base64 string. Raises CloudAuthError on failure."""
    region = REGIONS[region_key]
    async with aiohttp.ClientSession() as session:
        for endpoint in ["getAuthKey", "regenerateAuthKey"]:
            url = region["base_url"] + f"/v2/binding/enduserapi/{endpoint}"
            async with session.post(url, data={"pk": product_key, "dk": device_key},
                                    headers={"Authorization": token}) as resp:
                body = await resp.json(content_type=None)
            if body.get("code") == 200:
                return body["data"]["authKey"]
    raise CloudAuthError(f"Failed to get authKey for {device_key}")
