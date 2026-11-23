"""Minimal SNMPv2c GET client using only the standard library.

Avoids pysnmp asyncio transport issues on Windows after repeated event-loop cycles.
"""

from __future__ import annotations

import random
import socket
from typing import Iterable


class SnmpError(RuntimeError):
    pass


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    if length < 0x100:
        return bytes([0x81, length])
    if length < 0x10000:
        return bytes([0x82, (length >> 8) & 0xFF, length & 0xFF])
    raise SnmpError(f"Length too large: {length}")


def _encode_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(value)) + value


def _encode_integer(value: int, tag: int = 0x02) -> bytes:
    if value == 0:
        return _encode_tlv(tag, b"\x00")

    negative = value < 0
    if negative:
        value = -value

    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    if negative:
        inverted = bytes((~b) & 0xFF for b in raw)
        carry = 1
        out = bytearray()
        for b in reversed(inverted):
            total = b + carry
            out.append(total & 0xFF)
            carry = total >> 8
        raw = bytes(reversed(out))
        if raw[0] & 0x80 == 0:
            raw = b"\xff" + raw
    elif raw[0] & 0x80:
        raw = b"\x00" + raw

    return _encode_tlv(tag, raw)


def _encode_octet_string(value: str | bytes) -> bytes:
    data = value.encode("latin-1") if isinstance(value, str) else value
    return _encode_tlv(0x04, data)


def _encode_null() -> bytes:
    return _encode_tlv(0x05, b"")


def _encode_oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.lstrip(".").split(".") if p]
    if len(parts) < 2:
        raise SnmpError(f"Invalid OID: {oid}")

    body = bytearray([40 * parts[0] + parts[1]])
    for number in parts[2:]:
        if number < 0:
            raise SnmpError(f"Invalid OID component: {number}")
        stack: list[int] = []
        stack.append(number & 0x7F)
        number >>= 7
        while number:
            stack.append(0x80 | (number & 0x7F))
            number >>= 7
        body.extend(reversed(stack))
    return _encode_tlv(0x06, bytes(body))


def _encode_sequence(items: bytes, tag: int = 0x30) -> bytes:
    return _encode_tlv(tag, items)


def _build_get_request(community: str, request_id: int, oids: Iterable[str]) -> bytes:
    varbinds = b"".join(
        _encode_sequence(_encode_oid(oid) + _encode_null()) for oid in oids
    )
    pdu = _encode_sequence(
        _encode_integer(request_id)
        + _encode_integer(0)
        + _encode_integer(0)
        + _encode_sequence(varbinds),
        tag=0xA0,
    )
    message = _encode_sequence(
        _encode_integer(1) + _encode_octet_string(community) + pdu
    )
    return message


def _build_set_request(
    community: str,
    request_id: int,
    bindings: list[tuple[str, int]],
) -> bytes:
    """Build SNMPv2c SetRequest for integer OID values."""
    varbinds = b"".join(
        _encode_sequence(_encode_oid(oid) + _encode_integer(value))
        for oid, value in bindings
    )
    pdu = _encode_sequence(
        _encode_integer(request_id)
        + _encode_integer(0)
        + _encode_integer(0)
        + _encode_sequence(varbinds),
        tag=0xA3,  # SetRequest-PDU
    )
    return _encode_sequence(
        _encode_integer(1) + _encode_octet_string(community) + pdu
    )


def _read_length(data: bytes, index: int) -> tuple[int, int]:
    first = data[index]
    index += 1
    if first < 0x80:
        return first, index
    count = first & 0x7F
    if count == 0 or count > 3:
        raise SnmpError("Unsupported BER length")
    length = 0
    for _ in range(count):
        length = (length << 8) | data[index]
        index += 1
    return length, index


def _read_tlv(data: bytes, index: int) -> tuple[int, bytes, int]:
    tag = data[index]
    index += 1
    length, index = _read_length(data, index)
    value = data[index : index + length]
    return tag, value, index + length


def _decode_integer(value: bytes) -> int:
    if not value:
        return 0
    return int.from_bytes(value, "big", signed=True)


def _decode_oid(value: bytes) -> str:
    if not value:
        return ""
    first = value[0]
    parts = [first // 40, first % 40]
    number = 0
    for byte in value[1:]:
        number = (number << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            parts.append(number)
            number = 0
    return ".".join(str(p) for p in parts)


def _decode_varbind_value(tag: int, value: bytes) -> int | str | None:
    if tag == 0x02:
        return _decode_integer(value)
    if tag == 0x04:
        return value.decode("latin-1", errors="replace")
    if tag == 0x05:
        return None
    if tag == 0x06:
        return _decode_oid(value)
    if tag in (0x40, 0x41, 0x42, 0x43):
        return _decode_integer(value)
    if tag == 0x46:
        return int.from_bytes(value, "big", signed=False)
    if tag in (0x80, 0x81, 0x82):
        raise SnmpError("OID not found on device")
    try:
        return _decode_integer(value)
    except Exception as error:
        raise SnmpError(f"Unsupported SNMP value tag 0x{tag:02x}") from error


def _parse_get_response(data: bytes, expected_id: int) -> dict[str, int | str | None]:
    tag, value, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise SnmpError("Response is not an SNMP message")

    index = 0
    tag, _ver, index = _read_tlv(value, index)
    tag, _community, index = _read_tlv(value, index)
    tag, pdu, index = _read_tlv(value, index)
    if tag not in (0xA2, 0xA1, 0xA0):
        raise SnmpError(f"Unexpected PDU tag 0x{tag:02x}")

    pdu_index = 0
    tag, req_raw, pdu_index = _read_tlv(pdu, pdu_index)
    request_id = _decode_integer(req_raw)
    if request_id != expected_id:
        raise SnmpError(f"Request ID mismatch: {request_id} != {expected_id}")

    tag, err_raw, pdu_index = _read_tlv(pdu, pdu_index)
    error_status = _decode_integer(err_raw)
    tag, _err_index_raw, pdu_index = _read_tlv(pdu, pdu_index)
    if error_status != 0:
        raise SnmpError(f"SNMP error-status={error_status}")

    tag, varbind_list, pdu_index = _read_tlv(pdu, pdu_index)
    if tag != 0x30:
        raise SnmpError("Invalid varbind list")

    results: dict[str, int | str | None] = {}
    vb_index = 0
    while vb_index < len(varbind_list):
        tag, vb, vb_index = _read_tlv(varbind_list, vb_index)
        if tag != 0x30:
            raise SnmpError("Invalid varbind")
        inner = 0
        tag, oid_raw, inner = _read_tlv(vb, inner)
        oid = _decode_oid(oid_raw)
        tag, val_raw, inner = _read_tlv(vb, inner)
        results[oid] = _decode_varbind_value(tag, val_raw)

    return results


def snmp_get(
    host: str,
    community: str,
    oids: list[str],
    port: int = 161,
    timeout: float = 5.0,
    retries: int = 2,
) -> dict[str, int | str | None]:
    """Perform one SNMPv2c GetRequest for all OIDs and return oid->value."""
    if not oids:
        return {}

    request_id = random.randint(1, 0x7FFFFFFF)
    packet = _build_get_request(community, request_id, oids)

    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.sendto(packet, (host, port))
                data, _addr = sock.recvfrom(65535)
                return _parse_get_response(data, request_id)
            except Exception as error:
                last_error = error
                continue

    raise SnmpError(f"SNMP GET failed for {host}: {last_error}")


def _build_getnext_request(community: str, request_id: int, oid: str) -> bytes:
    varbinds = _encode_sequence(_encode_oid(oid) + _encode_null())
    pdu = _encode_sequence(
        _encode_integer(request_id)
        + _encode_integer(0)
        + _encode_integer(0)
        + _encode_sequence(varbinds),
        tag=0xA1,  # GetNextRequest-PDU
    )
    return _encode_sequence(_encode_integer(1) + _encode_octet_string(community) + pdu)


def _parse_getnext_response(data: bytes, expected_id: int) -> tuple[str, int | str | None]:
    tag, value, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise SnmpError("Response is not an SNMP message")
    index = 0
    tag, _ver, index = _read_tlv(value, index)
    tag, _community, index = _read_tlv(value, index)
    tag, pdu, index = _read_tlv(value, index)
    if tag not in (0xA2, 0xA1, 0xA0):
        raise SnmpError(f"Unexpected PDU tag 0x{tag:02x}")
    pdu_index = 0
    tag, req_raw, pdu_index = _read_tlv(pdu, pdu_index)
    if _decode_integer(req_raw) != expected_id:
        raise SnmpError("Request ID mismatch")
    tag, err_raw, pdu_index = _read_tlv(pdu, pdu_index)
    if _decode_integer(err_raw) != 0:
        raise SnmpError(f"SNMP error-status={_decode_integer(err_raw)}")
    tag, _err_index, pdu_index = _read_tlv(pdu, pdu_index)
    tag, varbind_list, pdu_index = _read_tlv(pdu, pdu_index)
    tag, vb, _ = _read_tlv(varbind_list, 0)
    inner = 0
    tag, oid_raw, inner = _read_tlv(vb, inner)
    oid = _decode_oid(oid_raw)
    tag, val_raw, inner = _read_tlv(vb, inner)
    if tag in (0x80, 0x81, 0x82):
        raise SnmpError("end of mib")
    return oid, _decode_varbind_value(tag, val_raw)


def snmp_getnext(
    host: str,
    community: str,
    oid: str,
    port: int = 161,
    timeout: float = 5.0,
    retries: int = 1,
) -> tuple[str, int | str | None]:
    """SNMPv2c GetNext. Read only."""
    request_id = random.randint(1, 0x7FFFFFFF)
    packet = _build_getnext_request(community, request_id, oid)
    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.sendto(packet, (host, port))
                data, _addr = sock.recvfrom(65535)
                return _parse_getnext_response(data, request_id)
            except Exception as error:
                last_error = error
                continue
    raise SnmpError(f"SNMP GETNEXT failed for {host}: {last_error}")


def snmp_set(
    host: str,
    community: str,
    bindings: list[tuple[str, int]],
    port: int = 161,
    timeout: float = 5.0,
    retries: int = 2,
) -> dict[str, int | str | None]:
    """Perform one SNMPv2c SetRequest for integer OID bindings."""
    if not bindings:
        return {}

    request_id = random.randint(1, 0x7FFFFFFF)
    packet = _build_set_request(community, request_id, bindings)

    last_error: Exception | None = None
    for _attempt in range(retries + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.sendto(packet, (host, port))
                data, _addr = sock.recvfrom(65535)
                return _parse_get_response(data, request_id)
            except Exception as error:
                last_error = error
                continue

    raise SnmpError(f"SNMP SET failed for {host}: {last_error}")
