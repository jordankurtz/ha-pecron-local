# custom_components/pecron_local/transport/tcp.py
"""Async TCP transport for Pecron devices on port 6607 (AES-CBC encrypted TTLV).

Ported from https://github.com/attractify-logan/pecron-monitor (MIT License).
Uses asyncio streams and the cryptography package (both bundled with HA).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import struct

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
from ..const import DEFAULT_PORT
from .base import PecronTransport, TransportError

_LOGGER = logging.getLogger(__name__)


class TcpTransport(PecronTransport):
    """Async TCP transport. Keeps socket open between polls; reconnects on error."""

    def __init__(
        self,
        host: str,
        auth_key_b64: str,
        port: int = DEFAULT_PORT,
        timeout: float = 10.0,
        controls: dict | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_key = base64.b64decode(auth_key_b64)
        self.timeout = timeout
        self.controls = controls

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._iv: bytes | None = None
        self._encrypted = False
        self._packet_id = 0
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._encrypted and self._writer is not None

    def _next_pid(self) -> int:
        self._packet_id = (self._packet_id + 1) % 65535
        return self._packet_id

    async def connect(self) -> None:
        await self.disconnect()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except Exception as exc:
            raise TransportError(f"TCP connect failed: {exc}") from exc

        try:
            await self._handshake()
        except TransportError:
            await self.disconnect()
            raise

    async def _handshake(self) -> None:
        # Step 1: request random IV
        await self._send_raw(build_iv_request(self._next_pid()))
        resp_raw = await self._recv_packet()
        resp = parse_packet(resp_raw)
        if resp.get("cmd") != 0x7033:
            raise TransportError(f"Expected 0x7033, got 0x{resp.get('cmd', 0):04x}")

        fields = parse_fields(resp["payload"])
        random_str = extract_iv_from_fields(fields)
        if not random_str:
            raise TransportError("No IV in 0x7033 response")

        # Step 2: login
        login_pkt = build_login_packet(self._next_pid(), self.auth_key, random_str)
        await self._send_raw(login_pkt)
        resp_raw = await self._recv_packet()
        resp = parse_packet(resp_raw)
        if resp.get("cmd") != 0x7035:
            raise TransportError(f"Login failed — expected 0x7035, got 0x{resp.get('cmd', 0):04x}")

        fields = parse_fields(resp["payload"])
        for _, ftype, fval in fields:
            if ftype == "NUM" and fval != 0:
                raise TransportError(f"Login rejected (result={fval})")

        self._iv = derive_iv(random_str)
        self._encrypted = True
        _LOGGER.debug("TCP handshake complete for %s:%s", self.host, self.port)

    async def disconnect(self) -> None:
        self._encrypted = False
        self._iv = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    async def _send_raw(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()

    async def _recv_packet(self) -> bytes:
        assert self._reader is not None
        buf = b""
        # Sync to 0xAA 0xAA
        while True:
            b = await asyncio.wait_for(self._reader.read(1), timeout=self.timeout)
            if not b:
                raise TransportError("Connection closed")
            buf += b
            if len(buf) >= 2 and buf[-2:] == b"\xaa\xaa":
                buf = b"\xaa\xaa"
                break
            if len(buf) > 200:
                raise TransportError("No sync found in stream")

        # Read 2-byte length
        len_raw = b""
        while len(len_raw) < 2:
            b = await asyncio.wait_for(self._reader.read(1), timeout=self.timeout)
            if not b:
                raise TransportError("Connection closed")
            buf += b
            if buf[-2] == 0xAA and b[0] == 0x55:
                continue
            len_raw += b

        pkt_len = struct.unpack(">H", len_raw)[0]
        remaining = pkt_len
        while remaining > 0:
            chunk = await asyncio.wait_for(
                self._reader.read(min(remaining, 4096)), timeout=self.timeout
            )
            if not chunk:
                raise TransportError("Connection closed mid-packet")
            buf += chunk
            remaining -= len(chunk)

        return buf

    async def read(self) -> dict:
        if not self.connected:
            raise TransportError("Not connected")
        async with self._lock:
            try:
                return await self._do_read()
            except TransportError:
                # Device closes TCP connection after each response — mark as
                # disconnected so the coordinator reconnects on the next poll.
                self._encrypted = False
                self._iv = None
                raise
            except Exception as exc:
                self._encrypted = False
                self._iv = None
                raise TransportError(f"Read failed: {exc}") from exc

    async def _do_read(self) -> dict:
        await self._send_raw(build_read_packet(self._next_pid()))

        all_fields: list = []
        await asyncio.sleep(0.1)

        for _ in range(10):
            try:
                resp_raw = await asyncio.wait_for(self._recv_packet(), timeout=3.0)
            except asyncio.TimeoutError:
                break
            resp = parse_packet(resp_raw)
            cmd = resp.get("cmd", 0)
            if cmd == 0x0012:
                continue
            if cmd == 0x0014:
                payload = resp.get("payload", b"")
                if payload:
                    decrypted = aes_decrypt(self.auth_key, self._iv, payload)
                    all_fields.extend(parse_fields(decrypted))
            else:
                break

        if not all_fields:
            _LOGGER.debug("No fields in TCP read from %s", self.host)
            return {}

        return fields_to_kv(all_fields, controls=self.controls)

    async def write(self, data_point_id: int, value: object, ctrl_type: str) -> None:
        if not self.connected:
            raise TransportError("Not connected")
        async with self._lock:
            try:
                await self._do_write(data_point_id, value, ctrl_type)
            except Exception as exc:
                self._encrypted = False
                raise TransportError(f"Write failed: {exc}") from exc

    async def _do_write(self, data_point_id: int, value: object, ctrl_type: str) -> None:
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
        await self._send_raw(pkt)
        await asyncio.wait_for(self._recv_packet(), timeout=5.0)
