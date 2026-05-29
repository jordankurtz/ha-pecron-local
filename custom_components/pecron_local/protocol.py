# custom_components/pecron_local/protocol.py
"""TTLV protocol encode/decode and AES-CBC helpers for Pecron local transport.

Ported from https://github.com/attractify-logan/pecron-monitor (MIT License).
"""
from __future__ import annotations

import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from .const import TSL_TOP, TSL_STRUCT


# ---------------------------------------------------------------------------
# AES-CBC helpers (uses cryptography, already bundled with HA)
# ---------------------------------------------------------------------------

def aes_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def aes_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(data) + dec.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def derive_iv(random_str: str) -> bytes:
    """Pad or truncate the device's random string to a 16-byte AES IV."""
    iv = random_str.encode("utf-8")
    if len(iv) < 16:
        iv = iv.ljust(16, b"\x00")
    return iv[:16]


# ---------------------------------------------------------------------------
# TTLV framing (byte stuffing)
# ---------------------------------------------------------------------------

def _byte_stuff(raw: bytes) -> bytes:
    out = bytearray(raw[:2])
    i = 2
    while i < len(raw):
        out.append(raw[i])
        if i < len(raw) - 1 and raw[i] == 0xAA and raw[i + 1] in (0x55, 0xAA):
            out.append(0x55)
        i += 1
    return bytes(out)


def _byte_unstuff(raw: bytes) -> bytes:
    out = bytearray(raw[:2])
    i = 2
    while i < len(raw):
        if i < len(raw) - 1 and raw[i] == 0xAA and raw[i + 1] == 0x55:
            out.append(0xAA)
            i += 2
        else:
            out.append(raw[i])
            i += 1
    return bytes(out)


def _build_packet(packet_id: int, cmd: int, payload: bytes = b"") -> bytes:
    inner = struct.pack(">HH", packet_id, cmd) + payload
    crc = sum(inner) & 0xFF
    length = len(inner) + 1
    return _byte_stuff(b"\xaa\xaa" + struct.pack(">H", length) + bytes([crc]) + inner)


def _build_bytes_field(tag_id: int, data: bytes) -> bytes:
    tag_word = ((tag_id << 3) & 0xFFF8) | 3
    return struct.pack(">H", tag_word) + struct.pack(">H", len(data)) + data


# ---------------------------------------------------------------------------
# Public packet builders
# ---------------------------------------------------------------------------

def build_read_packet(packet_id: int = 1) -> bytes:
    """cmd=0x0011: request device status."""
    return _build_packet(packet_id, 0x0011)


def build_write_bool_packet(packet_id: int, data_point_id: int, value: bool) -> bytes:
    """cmd=0x0013: write a boolean data point (unencrypted tag only)."""
    tag = (data_point_id << 3) | (1 if value else 0)
    payload = struct.pack(">H", tag)
    return _build_packet(packet_id, 0x0013, payload)


def build_write_enum_packet(packet_id: int, data_point_id: int, value: int) -> bytes:
    """cmd=0x0013: write an enum/int data point (unencrypted)."""
    tag = (data_point_id << 3) | 2
    payload = struct.pack(">H", tag) + bytes([int(value)])
    return _build_packet(packet_id, 0x0013, payload)


def build_login_payload(auth_key: bytes, random_str: str) -> bytes:
    """Build the login payload: SHA-256(auth_hex;random_str) in TTLV bytes field."""
    import hashlib
    auth_hex = auth_key.hex()
    login_hash = hashlib.sha256(f"{auth_hex};{random_str}".encode()).hexdigest()
    return _build_bytes_field(2, login_hash.encode("utf-8"))


def build_iv_request(packet_id: int) -> bytes:
    """cmd=0x7032: request random IV from device."""
    return _build_packet(packet_id, 0x7032)


def build_login_packet(packet_id: int, auth_key: bytes, random_str: str) -> bytes:
    """cmd=0x7034: send SHA-256 login hash."""
    return _build_packet(packet_id, 0x7034, build_login_payload(auth_key, random_str))


# ---------------------------------------------------------------------------
# Packet parsing
# ---------------------------------------------------------------------------

def parse_packet(data: bytes) -> dict:
    data = _byte_unstuff(data)
    if len(data) < 9 or data[0] != 0xAA or data[1] != 0xAA:
        return {"error": "bad packet", "raw": data.hex()}
    pkt_len = struct.unpack(">H", data[2:4])[0]
    pid = struct.unpack(">H", data[5:7])[0]
    cmd = struct.unpack(">H", data[7:9])[0]
    payload = data[9: 4 + pkt_len] if len(data) >= 4 + pkt_len else data[9:]
    return {"cmd": cmd, "packet_id": pid, "payload": payload}


def parse_fields(payload: bytes) -> list[tuple]:
    """Parse TTLV fields. Returns list of (id, type, value)."""
    fields = []
    i = 0
    while i < len(payload) - 1:
        tag_word = struct.unpack(">H", payload[i: i + 2])[0]
        tag_id = (tag_word >> 3) & 0x1FFF
        tag_type = tag_word & 0x07
        i += 2

        if tag_type in (0, 1):
            fields.append((tag_id, "BOOL", tag_type == 1))
        elif tag_type == 2:
            if i >= len(payload):
                break
            meta = payload[i]
            i += 1
            sign = (meta >> 7) & 1
            decimals = (meta >> 3) & 0x0F
            byte_count = (meta & 0x07) + 1
            if i + byte_count > len(payload):
                break
            val = int.from_bytes(payload[i: i + byte_count], "big")
            i += byte_count
            if sign:
                val = -val
            if decimals > 0:
                val = val / (10 ** decimals)
            fields.append((tag_id, "NUM", val))
        elif tag_type in (3, 5):
            if i + 2 > len(payload):
                break
            dlen = struct.unpack(">H", payload[i: i + 2])[0]
            i += 2
            fields.append((tag_id, "BYTES", payload[i: i + dlen]))
            i += dlen
        elif tag_type == 4:
            if i + 2 > len(payload):
                break
            count = struct.unpack(">H", payload[i: i + 2])[0]
            i += 2
            fields.append((tag_id, "STRUCT", count))
        else:
            break

    return fields


def extract_iv_from_fields(fields: list[tuple]) -> str | None:
    """Extract the random IV string from a 0x7033 response payload fields."""
    for fid, ftype, fval in fields:
        if fid == 1 and isinstance(fval, bytes):
            return fval.decode("utf-8")
    return None


def fields_to_kv(fields: list[tuple], controls: dict | None = None) -> dict:
    """Convert parsed TTLV fields to nested dict matching MQTT SENSOR_FIELDS paths.

    Ported from local_transport._fields_to_kv in pecron-monitor.
    """
    kv: dict = {}
    id_to_code: dict[int, str] = {}
    if controls:
        for code, info in controls.items():
            cid = info.get("id")
            if isinstance(cid, int):
                id_to_code[cid] = code

    i = 0
    while i < len(fields):
        fid, ftype, fval = fields[i]
        code = id_to_code.get(fid, TSL_TOP.get(fid))
        if code is None:
            i += 1
            continue

        if ftype == "STRUCT":
            sub_map = TSL_STRUCT.get(code, {})
            sub_dict: dict = {}
            count = fval
            j = i + 1
            consumed = 0
            is_array = False

            while j < len(fields) and consumed < count:
                sid, stype, sval = fields[j]
                sub_code = sub_map.get(sid, f"field_{sid}")
                if stype == "STRUCT" and code == "charging_pack_data_jdb":
                    packs = kv.get(code, [])
                    pack: dict = {}
                    elem_count = sval
                    k = j + 1
                    ec = 0
                    while k < len(fields) and ec < elem_count:
                        eid, etype, eval_ = fields[k]
                        if etype != "STRUCT":
                            pack[sub_map.get(eid, f"field_{eid}")] = eval_
                            ec += 1
                        k += 1
                    packs.append(pack)
                    kv[code] = packs
                    is_array = True
                    j = k
                    consumed += 1
                    continue
                sub_dict[sub_code] = sval
                j += 1
                consumed += 1

            if not is_array and not isinstance(kv.get(code), list):
                kv[code] = sub_dict
            i = j
        elif ftype == "BOOL":
            kv[code] = fval
            i += 1
        elif ftype == "NUM":
            kv[code] = fval
            i += 1
        elif ftype == "BYTES":
            try:
                kv[code] = fval.decode("utf-8")
            except Exception:
                kv[code] = fval.hex()
            i += 1
        else:
            kv[code] = fval
            i += 1

    return kv
