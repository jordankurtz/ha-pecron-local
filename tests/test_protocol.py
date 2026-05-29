# tests/test_protocol.py
import pytest
from custom_components.pecron_local.protocol import (
    build_read_packet,
    build_write_bool_packet,
    build_write_enum_packet,
    parse_packet,
    parse_fields,
    aes_encrypt,
    aes_decrypt,
    fields_to_kv,
)


def test_build_read_packet_starts_with_sync():
    pkt = build_read_packet(packet_id=1)
    assert pkt[:2] == b"\xaa\xaa"


def test_build_read_packet_cmd():
    pkt = build_read_packet(packet_id=1)
    parsed = parse_packet(pkt)
    assert parsed["cmd"] == 0x0011
    assert parsed["packet_id"] == 1


def test_build_write_bool_true():
    pkt = build_write_bool_packet(packet_id=2, data_point_id=40, value=True)
    parsed = parse_packet(pkt)
    assert parsed["cmd"] == 0x0013


def test_build_write_bool_false():
    pkt = build_write_bool_packet(packet_id=3, data_point_id=38, value=False)
    parsed = parse_packet(pkt)
    assert parsed["cmd"] == 0x0013


def test_build_write_enum():
    pkt = build_write_enum_packet(packet_id=4, data_point_id=50, value=5)
    parsed = parse_packet(pkt)
    assert parsed["cmd"] == 0x0013


def test_parse_packet_bad_sync():
    result = parse_packet(b"\x00\x00\x00\x00")
    assert "error" in result


def test_aes_roundtrip():
    key = b"0123456789abcdef"
    iv = b"fedcba9876543210"
    plaintext = b"hello pecron!!!"  # 15 bytes — needs padding
    encrypted = aes_encrypt(key, iv, plaintext)
    assert encrypted != plaintext
    decrypted = aes_decrypt(key, iv, encrypted)
    assert decrypted == plaintext


def test_aes_encrypt_is_padded_to_block():
    key = b"0123456789abcdef"
    iv = b"fedcba9876543210"
    plaintext = b"x"
    encrypted = aes_encrypt(key, iv, plaintext)
    assert len(encrypted) % 16 == 0


def test_byte_stuffing_roundtrip():
    # Packet containing 0xAA 0xAA — should be stuffed/unstuffed correctly
    pkt = build_read_packet(packet_id=0xAA)
    parsed = parse_packet(pkt)
    assert parsed.get("error") is None


def test_fields_to_kv_battery_percent():
    # Simulate fields: id=1 (battery_percentage), NUM, 85
    result = fields_to_kv([(1, "NUM", 85)])
    assert result.get("battery_percentage") == 85


def test_fields_to_kv_ac_switch_bool():
    # id=40 (ac_switch_hm), BOOL, True
    result = fields_to_kv([(40, "BOOL", True)])
    assert result.get("ac_switch_hm") is True


def test_parse_fields_bool_true():
    # Build a write-bool packet, extract payload, parse fields
    # BOOL true for id=40: tag = (40 << 3) | 1 = 321 = 0x0141
    import struct
    tag_word = (40 << 3) | 1
    payload = struct.pack(">H", tag_word)
    fields = parse_fields(payload)
    assert len(fields) == 1
    fid, ftype, fval = fields[0]
    assert fid == 40
    assert ftype == "BOOL"
    assert fval is True


def test_parse_fields_bool_false():
    import struct
    tag_word = (38 << 3) | 0
    payload = struct.pack(">H", tag_word)
    fields = parse_fields(payload)
    assert fields[0] == (38, "BOOL", False)
