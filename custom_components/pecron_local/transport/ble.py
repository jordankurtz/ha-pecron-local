# custom_components/pecron_local/transport/ble.py
"""BLE transport for Pecron devices using bleak (bundled with HA).

Ported from https://github.com/attractify-logan/pecron-monitor (MIT License).
Original used gatttool/pexpect; this uses bleak for HA compatibility.
Connects fresh each poll — persistent BLE connections are unreliable on Pecron firmware.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import struct

from bleak import BleakClient, BleakError

from ..const import BLE_CHAR_UUID
from ..protocol import (
    _byte_stuff,
    aes_decrypt,
    aes_encrypt,
    build_iv_request,
    build_login_packet,
    build_read_packet,
    derive_iv,
    extract_iv_from_fields,
    fields_to_kv,
    parse_fields,
    parse_packet,
)
from .base import PecronTransport, TransportError

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 15.0
_READ_TIMEOUT = 12.0


class BleTransport(PecronTransport):
    """BLE transport. Connects fresh each poll via bleak."""

    def __init__(
        self,
        mac: str,
        auth_key_b64: str,
        controls: dict | None = None,
    ) -> None:
        self.mac = mac
        self.auth_key = base64.b64decode(auth_key_b64)
        self.controls = controls

        self._client: BleakClient | None = None
        self._iv: bytes | None = None
        self._encrypted = False
        self._packet_id = 0
        self._notify_queue: asyncio.Queue[bytes] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        return self._encrypted and self._client is not None

    def _next_pid(self) -> int:
        self._packet_id = (self._packet_id + 1) % 65535
        return self._packet_id

    def _on_notify(self, _handle: int, data: bytes) -> None:
        self._notify_queue.put_nowait(data)

    async def _collect_indications(self, wait: float = 5.0) -> bytes:
        """Collect all queued indication bytes up to `wait` seconds after last packet."""
        accumulated = b""
        deadline = asyncio.get_running_loop().time() + wait
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                chunk = await asyncio.wait_for(
                    self._notify_queue.get(), timeout=min(remaining, 1.0)
                )
                accumulated += chunk
                # Extend deadline on each received chunk (more may follow)
                deadline = asyncio.get_running_loop().time() + 2.0
            except asyncio.TimeoutError:
                if accumulated:
                    break
        return accumulated

    async def _write_char(self, data: bytes) -> None:
        assert self._client is not None
        try:
            await self._client.write_gatt_char(BLE_CHAR_UUID, data, response=True)
        except BleakError as exc:
            raise TransportError(f"BLE write failed: {exc}") from exc

    def _parse_all_packets(self, raw: bytes) -> list[dict]:
        packets = []
        i = 0
        while i < len(raw) - 4:
            if raw[i] == 0xAA and raw[i + 1] == 0xAA:
                pkt_len = struct.unpack(">H", raw[i + 2: i + 4])[0]
                total = 4 + pkt_len
                if i + total <= len(raw):
                    packets.append(parse_packet(raw[i: i + total]))
                i += total
            else:
                i += 1
        return packets

    async def connect(self) -> None:
        await self.disconnect()
        try:
            self._client = BleakClient(self.mac, timeout=_CONNECT_TIMEOUT)
            await self._client.connect()
            await self._client.start_notify(BLE_CHAR_UUID, self._on_notify)
        except Exception as exc:
            await self.disconnect()
            raise TransportError(f"BLE connect failed: {exc}") from exc

        try:
            await self._handshake()
        except TransportError:
            await self.disconnect()
            raise

    async def _handshake(self) -> None:
        # Drain any stale notifications
        while not self._notify_queue.empty():
            self._notify_queue.get_nowait()

        # Request IV
        await self._write_char(build_iv_request(self._next_pid()))
        raw = await self._collect_indications(wait=5.0)
        if not raw:
            raise TransportError("BLE: no IV response")

        packets = self._parse_all_packets(raw)
        random_str = None
        for pkt in packets:
            if pkt.get("cmd") == 0x7033:
                fields = parse_fields(pkt.get("payload", b""))
                random_str = extract_iv_from_fields(fields)
                break

        if not random_str:
            raise TransportError("BLE: could not extract IV")

        # Login
        login_pkt = build_login_packet(self._next_pid(), self.auth_key, random_str)
        await self._write_char(login_pkt)
        raw = await self._collect_indications(wait=5.0)

        packets = self._parse_all_packets(raw)
        for pkt in packets:
            if pkt.get("cmd") == 0x7035:
                self._iv = derive_iv(random_str)
                self._encrypted = True
                _LOGGER.debug("BLE handshake complete for %s", self.mac)
                return

        raise TransportError("BLE: login response not received or rejected")

    async def disconnect(self) -> None:
        self._encrypted = False
        self._iv = None
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def read(self) -> dict:
        if not self.connected:
            raise TransportError("Not connected")
        try:
            return await self._do_read()
        except TransportError:
            self._encrypted = False
            raise
        except Exception as exc:
            self._encrypted = False
            raise TransportError(f"BLE read failed: {exc}") from exc

    async def _do_read(self) -> dict:
        # Drain stale notifications
        while not self._notify_queue.empty():
            self._notify_queue.get_nowait()

        await self._write_char(build_read_packet(self._next_pid()))
        raw = await self._collect_indications(wait=_READ_TIMEOUT)

        if not raw:
            raise TransportError("BLE: no read response")

        all_fields: list = []
        for pkt in self._parse_all_packets(raw):
            payload = pkt.get("payload", b"")
            if not payload or len(payload) < 16:
                continue
            try:
                decrypted = aes_decrypt(self.auth_key, self._iv, payload)
                all_fields.extend(parse_fields(decrypted))
            except Exception:
                try:
                    all_fields.extend(parse_fields(payload))
                except Exception:
                    pass

        if not all_fields:
            _LOGGER.debug("BLE: no parseable fields from %s", self.mac)
            return {}

        return fields_to_kv(all_fields, controls=self.controls)

    async def write(self, data_point_id: int, value: object, ctrl_type: str) -> None:
        if not self.connected:
            raise TransportError("Not connected")
        ctrl_type = ctrl_type.upper()
        if ctrl_type == "BOOL":
            raw_payload = struct.pack(">H", (data_point_id << 3) | (1 if value else 0))
        else:
            raw_payload = struct.pack(">H", (data_point_id << 3) | 2) + bytes([int(value)])

        enc_payload = aes_encrypt(self.auth_key, self._iv, raw_payload)
        inner = struct.pack(">HH", self._next_pid(), 0x0013) + enc_payload
        crc = sum(inner) & 0xFF
        length = len(inner) + 1
        raw_pkt = b"\xaa\xaa" + struct.pack(">H", length) + bytes([crc]) + inner
        pkt = _byte_stuff(raw_pkt)
        await self._write_char(pkt)
