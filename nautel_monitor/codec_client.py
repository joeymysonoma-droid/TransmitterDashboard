"""Read-only polls for Comrex ACCESS, BRIC-Link, and Inovonics Instream.

Comrex and BRIC-Link share the ACCESS web socket (subprotocol ComrexIPC).
This client sends hello, login, getUnitStatus, and getPeerList only.
It never sends connect, disconnect, or configuration writes.

An Inovonics 635 SiteStreamer is read with GET /status.json. That request
does not retune the receiver or change the audio source.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import urllib.request
from typing import Any

from .models import (
    AlarmState,
    MeterReading,
    StlDeviceConfig,
    StlReading,
    utc_now,
)

logger = logging.getLogger(__name__)

def poll_instream(
    device: StlDeviceConfig,
    *,
    timeout: float = 4.0,
    retries: int = 1,
) -> StlReading:
    del retries
    if not device.configured:
        return _offline(device, "Host is not configured")
    try:
        payload = _fetch_instream_status(device.host, timeout)
    except Exception as error:
        logger.info("Instream poll failed for %s: %s", device.host, error)
        return _offline(device, f"Instream status.json failed: {error}")
    return _instream_reading(device, payload)


def _fetch_instream_status(host: str, timeout: float) -> dict[str, Any]:
    import gzip

    request = urllib.request.Request(
        f"http://{host}/status.json",
        headers={"User-Agent": "ASMG-TX-Dashboard", "Accept-Encoding": "gzip"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8", "replace"))
    if not isinstance(payload, dict):
        raise ValueError("status.json was not an object")
    return payload


def _instream_reading(device: StlDeviceConfig, payload: dict[str, Any]) -> StlReading:
    alarms_raw = payload.get("alarms") if isinstance(payload.get("alarms"), list) else []
    audio_alarm = bool(alarms_raw[0]) if len(alarms_raw) > 0 else False
    rf_alarm = bool(alarms_raw[1]) if len(alarms_raw) > 1 else False
    rds_alarm = bool(alarms_raw[2]) if len(alarms_raw) > 2 else False
    pilot = alarms_raw[3] if len(alarms_raw) > 3 else None

    name = str(payload.get("crname") or "").strip()
    freq = payload.get("freq")
    freq_text = f"{float(freq):.1f} MHz" if isinstance(freq, (int, float)) else ""
    station = name or freq_text or device.name

    if rf_alarm and audio_alarm:
        link_state = "down"
        link_label = f"RF and audio loss · {station}"
    elif rf_alarm:
        link_state = "down"
        link_label = f"RF alarm · {station}"
    elif audio_alarm:
        link_state = "down"
        link_label = f"Audio loss · {station}"
    else:
        link_state = "up"
        bits = ["On air", station]
        freq_number = f"{float(freq):.1f}" if isinstance(freq, (int, float)) else ""
        if freq_text and freq_number and freq_number not in station:
            bits.append(freq_text)
        link_label = " · ".join(bit for bit in bits if bit)

    meters: list[MeterReading] = []
    levels = payload.get("lr") if isinstance(payload.get("lr"), list) else []
    peaks = payload.get("peaks") if isinstance(payload.get("peaks"), list) else []
    if len(levels) > 0 and isinstance(levels[0], (int, float)):
        meters.append(MeterReading("left_db", "Left", round(float(levels[0]), 1), "dB", "signal"))
    if len(levels) > 1 and isinstance(levels[1], (int, float)):
        meters.append(MeterReading("right_db", "Right", round(float(levels[1]), 1), "dB", "signal"))
    if isinstance(freq, (int, float)):
        meters.append(MeterReading("freq_mhz", "Frequency", round(float(freq), 2), "MHz", "signal"))
    if len(peaks) > 0 and isinstance(peaks[0], (int, float)):
        meters.append(MeterReading("peak_left_db", "Peak L", round(float(peaks[0]), 1), "dB", "signal"))
    if isinstance(pilot, (int, float)):
        meters.append(MeterReading("pilot", "Pilot", int(bool(pilot)), "", "signal"))

    alarms: list[AlarmState] = []
    if audio_alarm:
        alarms.append(AlarmState("audio_loss", "Audio loss", True))
    if rf_alarm:
        alarms.append(AlarmState("rf", "RF alarm", True))
    if rds_alarm:
        alarms.append(AlarmState("rds", "RDS alarm", True))
    if link_state == "down":
        alarms.insert(0, AlarmState("link_down", link_label, True))

    status = "online"
    if link_state != "up" or rds_alarm:
        status = "degraded"
    return StlReading(
        stl_id=device.id,
        timestamp=utc_now(),
        reachable=True,
        status=status,
        host=device.host,
        name=device.name,
        model=device.model,
        location=device.location,
        link_state=link_state,
        link_label=link_label,
        meters=meters,
        alarms=alarms,
        oid_ok=len(meters),
        oid_total=4,
        related_tx_id=device.related_tx_id,
    )


def poll_comrex(
    device: StlDeviceConfig,
    *,
    timeout: float = 5.0,
    retries: int = 1,
) -> StlReading:
    del retries
    if not device.configured:
        return _offline(device, "Host is not configured")
    if not (device.http_password or "").strip():
        return _auth_needed(device)
    try:
        return asyncio.run(_poll_comrex(device, timeout=timeout))
    except Exception as error:
        logger.info("Comrex poll failed for %s: %s", device.host, error)
        return _offline(device, f"Comrex websocket failed: {error}")


async def _poll_comrex(device: StlDeviceConfig, *, timeout: float) -> StlReading:
    import websockets

    messages: list[dict[str, Any]] = []
    async with websockets.connect(
        f"ws://{device.host}:80",
        subprotocols=["ComrexIPC"],
        open_timeout=min(timeout, 4.0),
        close_timeout=1,
        max_size=2_000_000,
    ) as ws:
        await ws.send(_comrex_msg("encoding", outbound="json"))
        await ws.send(_comrex_msg("hello", version=1, seq="hello"))
        challenge = None
        for _ in range(4):
            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=min(timeout, 4.0)))
            messages.append(data)
            params = data.get("params") or {}
            if params.get("challenge"):
                challenge = str(params["challenge"])
                break
        if not challenge:
            return _offline(device, "Comrex did not offer a login challenge", reachable=True)
        digest = hashlib.md5((challenge + device.http_password).encode()).hexdigest()
        await ws.send(
            _comrex_msg("login", username="", response=digest, seq="login")
        )
        login = json.loads(await asyncio.wait_for(ws.recv(), timeout=min(timeout, 4.0)))
        login_params = login.get("params") or {}
        if login_params.get("fail"):
            return _auth_needed(device, str(login_params.get("error_text") or "Login failed"))
        await ws.send(_comrex_msg("getUnitStatus", seq="unitStatus"))
        await ws.send(_comrex_msg("getPeerList", seq="peerList:*"))
        deadline = asyncio.get_running_loop().time() + min(timeout, 2.0)
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=min(0.8, remaining))
            except TimeoutError:
                break
            messages.append(json.loads(raw))
    return _comrex_reading(device, messages)


def _comrex_msg(name: str, **params: Any) -> str:
    return json.dumps({"name": name, "children": [], "params": params})


def _comrex_reading(device: StlDeviceConfig, messages: list[dict[str, Any]]) -> StlReading:
    peers: list[dict[str, Any]] = []
    unit_bits: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        name = str(node.get("name") or "")
        params = node.get("params") if isinstance(node.get("params"), dict) else {}
        if name.lower() in {"peer", "connection", "session", "remote"} and params:
            peers.append(params)
        for key in ("state", "status", "unit_name", "name", "descr"):
            value = params.get(key)
            if isinstance(value, str) and value and key != "seq":
                unit_bits.append(value)
        for child in node.get("children") or []:
            walk(child)

    for message in messages:
        walk(message)

    connected = []
    idle = []
    for peer in peers:
        blob = " ".join(str(value) for value in peer.values() if isinstance(value, str)).lower()
        if any(word in blob for word in ("connect", "active", "online")) and "disconnect" not in blob:
            connected.append(peer)
        else:
            idle.append(peer)

    if peers and connected and not idle:
        link_state = "up"
        label = f"{len(connected)}/{len(peers)} connections"
    elif peers and connected:
        link_state = "degraded"
        label = f"{len(connected)}/{len(peers)} connections"
    elif peers:
        link_state = "down"
        label = f"0/{len(peers)} connections"
    elif unit_bits:
        link_state = "unknown"
        label = unit_bits[0][:80]
    else:
        return _reachable_gap(device, "Comrex answered login but no status fields")

    meters = [
        MeterReading("connections", "Connections", len(connected), "", "stream"),
        MeterReading("peers", "Peers", len(peers), "", "stream"),
    ]
    alarms = []
    if link_state == "down":
        alarms.append(AlarmState("link_down", label, True))
    status = "online" if link_state == "up" else "degraded"
    return StlReading(
        stl_id=device.id,
        timestamp=utc_now(),
        reachable=True,
        status=status,
        host=device.host,
        name=device.name,
        model=device.model,
        location=device.location,
        link_state=link_state,
        link_label=label,
        meters=meters,
        alarms=alarms,
        oid_ok=2 if peers else 1,
        oid_total=3,
        related_tx_id=device.related_tx_id,
    )


def _offline(device: StlDeviceConfig, error: str, *, reachable: bool = False) -> StlReading:
    return StlReading(
        stl_id=device.id,
        timestamp=utc_now(),
        reachable=reachable,
        status="offline",
        host=device.host,
        name=device.name,
        model=device.model,
        location=device.location,
        link_state="unknown",
        link_label="Unreachable" if device.configured else "Not configured",
        error=error,
        related_tx_id=device.related_tx_id,
    )


def _auth_needed(device: StlDeviceConfig, detail: str = "Web password required") -> StlReading:
    return StlReading(
        stl_id=device.id,
        timestamp=utc_now(),
        reachable=True,
        status="degraded",
        host=device.host,
        name=device.name,
        model=device.model,
        location=device.location,
        link_state="unknown",
        link_label="Login required",
        error=detail,
        related_tx_id=device.related_tx_id,
    )


def _reachable_gap(device: StlDeviceConfig, error: str) -> StlReading:
    return StlReading(
        stl_id=device.id,
        timestamp=utc_now(),
        reachable=True,
        status="degraded",
        host=device.host,
        name=device.name,
        model=device.model,
        location=device.location,
        link_state="unknown",
        link_label="Unknown",
        error=error,
        related_tx_id=device.related_tx_id,
    )
