"""Crown / Ecreso FM TX via Audemat FmNgIp WebSocket (/wscom).

Login: JSON `login@auth` with Admin/admin (factory default).
Meters: JSON-RPC `config.getPartValuesHash` over the same socket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .models import AlarmState, MeterReading, TransmitterConfig, TransmitterReading, utc_now

logger = logging.getLogger(__name__)

DEFAULT_USER = "Admin"
DEFAULT_PASS = "admin"

METER_PATHS: tuple[str, ...] = (
    "sys.applications.fmngip.tx.pfwd",
    "sys.applications.fmngip.tx.pref",
    "sys.applications.fmngip.tx.vswr",
    "sys.applications.fmngip.tx.opmode",
    "sys.applications.fmngip.tx.rfPresent",
    "sys.applications.fmngip.tx.fault",
    "sys.applications.fmngip.tx.warning",
    "sys.applications.fmngip.tx.type",
    "sys.applications.fmngip.tx.name",
    "sys.applications.fmngip.tx.pwr",
    "sys.applications.fmngip.tx.pwrMax",
    "sys.applications.fmngip.meas.pfwd",
    "sys.applications.fmngip.meas.pref",
    "sys.applications.fmngip.meas.vswr",
    "sys.applications.fmngip.meas.heat1",
    "sys.applications.fmngip.meas.heat2",
    "sys.applications.fmngip.meas.amb",
    "sys.applications.fmngip.meas.cur1",
    "sys.applications.fmngip.meas.cur2",
    "sys.applications.fmngip.meas.volt1",
    "sys.applications.fmngip.meas.volt2",
)


class CrownError(RuntimeError):
    pass


def _dig(data: dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


async def _fetch_async(
    host: str,
    username: str,
    password: str,
    use_tls: bool = False,
    timeout: float = 8.0,
) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as error:
        raise CrownError("websockets package is required for Crown/Audemat polling") from error

    scheme = "wss" if use_tls else "ws"
    url = f"{scheme}://{host}/wscom"
    ssl_ctx = None
    if use_tls:
        import ssl as ssl_mod

        ssl_ctx = ssl_mod._create_unverified_context()

    async with websockets.connect(
        url,
        ssl=ssl_ctx,
        open_timeout=timeout,
        close_timeout=2,
        max_size=5_000_000,
        additional_headers=[("Origin", f"http://{host}")],
    ) as ws:
        await ws.send(
            json.dumps({"login@auth": {"login": username, "pass": password}}) + "\n"
        )
        auth = await asyncio.wait_for(ws.recv(), timeout=timeout)
        auth_obj = json.loads(auth)
        login = auth_obj.get("login@auth") or {}
        if not login.get("retVal"):
            raise CrownError(f"Login failed: {auth_obj}")

        req = {
            "jsonrpc@jsonrpc": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "config.getPartValuesHash",
                "params": [list(METER_PATHS), 0, 0],
            }
        }
        await ws.send(json.dumps(req) + "\n")
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        payload = json.loads(raw)
        body = payload.get("jsonrpc@jsonrpc") or {}
        if "error" in body:
            raise CrownError(f"RPC error: {body['error']}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise CrownError("Unexpected RPC result")
        return result


def fetch_values(
    host: str,
    username: str = DEFAULT_USER,
    password: str = DEFAULT_PASS,
    timeout: float = 8.0,
) -> dict[str, Any]:
    try:
        return asyncio.run(
            _fetch_async(host, username, password, use_tls=False, timeout=timeout)
        )
    except CrownError:
        raise
    except Exception as first:
        try:
            return asyncio.run(
                _fetch_async(host, username, password, use_tls=True, timeout=timeout)
            )
        except Exception as second:
            raise CrownError(f"WebSocket poll failed: {first}; TLS retry: {second}") from second


def poll_crown(tx: TransmitterConfig, timeout: float = 8.0) -> TransmitterReading:
    user = tx.http_username or DEFAULT_USER
    password = tx.http_password or DEFAULT_PASS
    try:
        data = fetch_values(tx.host, user, password, timeout=timeout)
    except CrownError as error:
        logger.warning("Crown poll failed for %s (%s): %s", tx.id, tx.host, error)
        return TransmitterReading(
            tx_id=tx.id,
            timestamp=utc_now(),
            status="offline",
            host=tx.host,
            name=tx.name,
            model=tx.model,
            location=tx.location,
            error=str(error),
        )

    tx_tree = _dig(data, "sys.applications.fmngip.tx") or {}
    meas = _dig(data, "sys.applications.fmngip.meas") or {}

    # Prefer live meas.*; fall back to tx.*
    fwd = _as_float(meas.get("pfwd", tx_tree.get("pfwd")))
    rfl = _as_float(meas.get("pref", tx_tree.get("pref")))
    vswr_raw = _as_float(meas.get("vswr", tx_tree.get("vswr")))
    vswr = (vswr_raw / 10.0) if vswr_raw is not None else None
    heat = _as_float(meas.get("heat1"))
    amb = _as_float(meas.get("amb"))
    cur1 = _as_float(meas.get("cur1"))
    cur2 = _as_float(meas.get("cur2"))
    volt1 = _as_float(meas.get("volt1"))
    volt2 = _as_float(meas.get("volt2"))
    pwr_set = _as_float(tx_tree.get("pwr"))
    pwr_max = _as_float(tx_tree.get("pwrMax"))
    opmode = _as_int(tx_tree.get("opmode"))
    rf_present = _as_int(tx_tree.get("rfPresent"))
    fault = _as_int(tx_tree.get("fault"))
    warning = _as_int(tx_tree.get("warning"))
    tx_type = str(tx_tree.get("type") or "").strip()

    meters: list[MeterReading] = [
        MeterReading("fwd_pwr_w", "Forward Power", fwd, "W", "rf"),
        MeterReading("rfl_pwr_w", "Reflected Power", rfl, "W", "rf"),
        MeterReading("vswr", "VSWR", vswr, "", "rf"),
        MeterReading("pwr_set_w", "Power Setpoint", pwr_set, "W", "rf"),
        MeterReading("pwr_max_w", "Power Capability", pwr_max, "W", "rf"),
        MeterReading("cur1", "Current 1", cur1, "", "pa"),
        MeterReading("cur2", "Current 2", cur2, "", "pa"),
        MeterReading("volt1", "Voltage 1", volt1, "V", "supply"),
        MeterReading("volt2", "Voltage 2", volt2, "V", "supply"),
        MeterReading("heatsink_temp_c", "Heatsink Temp", heat, "°C", "cooling"),
        MeterReading("ambient_temp_c", "Ambient Temp", amb, "°C", "cooling"),
        MeterReading("rf_present", "RF Present", rf_present, "", "control"),
        MeterReading("opmode", "RF Mode", opmode, "", "control"),
    ]
    if tx_type:
        meters.append(
            MeterReading("tx_type", f"TX Type ({tx_type})", 1, "", "control")
        )

    # Audemat often uses 1=asserted, 2=clear for alarm-like enums.
    alarms = [
        AlarmState("fault", "Transmitter Fault", fault == 1),
        AlarmState("warning", "Transmitter Warning", warning == 1),
        AlarmState("rf_missing", "RF Not Present", rf_present == 0),
    ]

    ok = sum(1 for m in meters if m.value is not None or m.unit)
    status = "online" if fwd is not None or opmode is not None else "degraded"

    return TransmitterReading(
        tx_id=tx.id,
        timestamp=utc_now(),
        status=status,
        host=tx.host,
        name=tx.name,
        model=tx.model,
        location=tx.location,
        fwd_pwr_w=fwd,
        rfl_pwr_w=rfl,
        vswr=vswr,
        heatsink_temp_c=heat,
        pa_volts_v=volt1,
        pa_current_1_a=cur1,
        rf_state=1 if opmode == 1 else 0 if opmode == 0 else opmode,
        meters=meters,
        alarms=alarms,
        oid_ok=ok,
        oid_total=len(meters),
    )
