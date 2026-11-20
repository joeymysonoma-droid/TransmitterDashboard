"""SNMPv2c GETNEXT walk under GatesAir Flexiva enterprise 43768."""

from __future__ import annotations

import random
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.snmp_client import (  # noqa: E402
    SnmpError,
    _build_get_request,
    _decode_integer,
    _decode_oid,
    _decode_varbind_value,
    _encode_integer,
    _encode_null,
    _encode_octet_string,
    _encode_oid,
    _encode_sequence,
    _read_tlv,
)


def _build_getnext(community: str, request_id: int, oid: str) -> bytes:
    varbinds = _encode_sequence(_encode_oid(oid) + _encode_null())
    pdu = _encode_sequence(
        _encode_integer(request_id)
        + _encode_integer(0)
        + _encode_integer(0)
        + _encode_sequence(varbinds),
        tag=0xA1,  # GetNextRequest-PDU
    )
    return _encode_sequence(_encode_integer(1) + _encode_octet_string(community) + pdu)


def _parse_getnext(data: bytes, expected_id: int) -> tuple[str, int | str | None]:
    tag, value, _ = _read_tlv(data, 0)
    if tag != 0x30:
        raise SnmpError("bad message")
    index = 0
    tag, _ver, index = _read_tlv(value, index)
    tag, _community, index = _read_tlv(value, index)
    tag, pdu, index = _read_tlv(value, index)
    pdu_index = 0
    tag, req_raw, pdu_index = _read_tlv(pdu, pdu_index)
    if _decode_integer(req_raw) != expected_id:
        raise SnmpError("request id mismatch")
    tag, err_raw, pdu_index = _read_tlv(pdu, pdu_index)
    if _decode_integer(err_raw) != 0:
        raise SnmpError(f"error-status={_decode_integer(err_raw)}")
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


def snmp_getnext(host: str, community: str, oid: str, port: int = 161, timeout: float = 2.5):
    request_id = random.randint(1, 0x7FFFFFFF)
    packet = _build_getnext(community, request_id, oid)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (host, port))
        data, _ = sock.recvfrom(65535)
    return _parse_getnext(data, request_id)


def walk(host: str, community: str, root: str, limit: int = 400) -> list[tuple[str, object]]:
    current = root
    out: list[tuple[str, object]] = []
    for _ in range(limit):
        try:
            nxt, value = snmp_getnext(host, community, current)
        except Exception as exc:  # noqa: BLE001
            print("STOP", current, exc)
            break
        if not nxt.startswith(root.rstrip(".")):
            break
        out.append((nxt, value))
        current = nxt
    return out


def main() -> None:
    host = "10.2.10.152"
    community = "public"
    root = "1.3.6.1.4.1.43768"
    rows = walk(host, community, root, limit=500)
    print(f"got {len(rows)} OIDs under {root}")
    for oid, value in rows:
        print(f"{oid} = {value!r}")


if __name__ == "__main__":
    main()
