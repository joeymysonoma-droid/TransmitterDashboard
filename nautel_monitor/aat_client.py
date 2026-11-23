"""American Amplifier Technologies (AAT) FM TX SNMP client.

OID map from aat_FM_Tx_1_1.mib (enterprise 51550), matching AAT_Monitor.
VSWR is reported in hundredths; power/temps are already engineering units.
RF on/off uses the web controller (same as AAT_Monitor), not SNMP SET.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from .models import AlarmState, MeterReading, TransmitterConfig, TransmitterReading, utc_now
from .snmp_client import SnmpError, snmp_get

logger = logging.getLogger(__name__)

ENTERPRISE = "1.3.6.1.4.1.51550"
TX_BASE = f"{ENTERPRISE}.4.2"

# key, leaf, label, unit, category, convert
# convert: "raw" | "vswr100" | "bool"
METER_SPECS: tuple[tuple[str, int, str, str, str, str], ...] = (
    ("fwd_pwr_w", 1, "Forward Power", "W", "rf", "raw"),
    ("rfl_pwr_w", 2, "Reflected Power", "W", "rf", "raw"),
    ("vswr", 3, "VSWR", "", "rf", "vswr100"),
    ("exc_drv_pwr_w", 12, "Exciter Drive Power", "W", "rf", "raw"),
    ("cur1_a", 4, "AC Current 1", "A", "pa", "raw"),
    ("cur2_a", 5, "AC Current 2", "A", "pa", "raw"),
    ("cur3_a", 6, "AC Current 3", "A", "pa", "raw"),
    ("vlt1_v", 7, "DC Voltage 1", "V", "supply", "raw"),
    ("vlt2_v", 8, "DC Voltage 2", "V", "supply", "raw"),
    ("vlt3_v", 9, "DC Voltage 3", "V", "supply", "raw"),
    ("heatsink_temp_c", 10, "Heatsink Temp", "°C", "cooling", "raw"),
    ("ambient_temp_c", 11, "Ambient Temp", "°C", "cooling", "raw"),
    ("amp_status", 14, "Amplifier Status", "", "control", "bool"),
)

ALARM_SPECS: tuple[tuple[str, int, str], ...] = (
    ("gen_fault", 13, "General Fault"),
)

OID_CHUNK = 4


def _oid(leaf: int) -> str:
    return f"{TX_BASE}.{leaf}.0"


def _convert(kind: str, raw: int) -> float | int | None:
    if kind == "vswr100":
        return raw / 100.0
    if kind == "bool":
        return 1 if raw else 0
    return float(raw)


def poll_aat(tx: TransmitterConfig, timeout: float = 3.0) -> TransmitterReading:
    oids = [_oid(leaf) for _, leaf, *_ in METER_SPECS] + [
        _oid(leaf) for _, leaf, _ in ALARM_SPECS
    ]
    raw: dict[str, int | str | None] = {}
    try:
        for start in range(0, len(oids), OID_CHUNK):
            chunk = oids[start : start + OID_CHUNK]
            raw.update(
                snmp_get(
                    host=tx.host,
                    community=tx.snmp_community,
                    oids=chunk,
                    port=tx.snmp_port,
                    timeout=timeout,
                    retries=1,
                )
            )
    except SnmpError as error:
        logger.warning("AAT SNMP failed for %s (%s): %s", tx.id, tx.host, error)
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

    meters: list[MeterReading] = []
    values: dict[str, float | int | None] = {}
    ok = 0
    for key, leaf, label, unit, category, kind in METER_SPECS:
        oid = _oid(leaf)
        raw_val = raw.get(oid)
        value: float | int | None = None
        if isinstance(raw_val, int):
            value = _convert(kind, raw_val)
            ok += 1
        values[key] = value
        meters.append(
            MeterReading(
                key=key,
                label=label,
                value=value,
                unit=unit,
                category=category,
            )
        )

    alarms: list[AlarmState] = []
    for key, leaf, label in ALARM_SPECS:
        oid = _oid(leaf)
        raw_val = raw.get(oid)
        active = isinstance(raw_val, int) and raw_val != 0
        if isinstance(raw_val, int):
            ok += 1
        alarms.append(AlarmState(key=key, label=label, active=active))

    total = len(METER_SPECS) + len(ALARM_SPECS)
    if ok == 0:
        status = "offline"
    elif ok < total:
        status = "degraded"
    else:
        status = "online"

    amp = values.get("amp_status")
    rf_state = int(amp) if amp is not None else None

    return TransmitterReading(
        tx_id=tx.id,
        timestamp=utc_now(),
        status=status,
        host=tx.host,
        name=tx.name,
        model=tx.model,
        location=tx.location,
        fwd_pwr_w=_as_float(values.get("fwd_pwr_w")),
        rfl_pwr_w=_as_float(values.get("rfl_pwr_w")),
        vswr=_as_float(values.get("vswr")),
        heatsink_temp_c=_as_float(values.get("heatsink_temp_c")),
        pa_volts_v=_as_float(values.get("vlt1_v")),
        pa_current_1_a=_as_float(values.get("cur1_a")),
        rf_state=rf_state,
        meters=meters,
        alarms=alarms,
        oid_ok=ok,
        oid_total=total,
    )


def _as_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


class AatControlError(RuntimeError):
    pass


def set_aat_rf(tx: TransmitterConfig, *, on: bool, timeout: float = 15.0) -> str:
    """Login to AAT web UI and POST rfControl on/off."""
    username = (tx.http_username or "admin").strip()
    password = tx.http_password or ""
    if not password:
        raise AatControlError(
            "AAT RF control needs http_username/http_password in transmitter config"
        )
    base = f"http://{tx.host}"
    if tx.http_port and tx.http_port != 80:
        base = f"http://{tx.host}:{tx.http_port}"

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    login_body = urllib.parse.urlencode(
        {
            "login": "true",
            "username": username,
            "password": password,
        }
    ).encode("utf-8")
    try:
        login_req = urllib.request.Request(
            f"{base}/cgi-bin/controller.py",
            data=login_body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with opener.open(login_req, timeout=timeout) as resp:
            if resp.status == 401:
                raise AatControlError("AAT web login failed: invalid credentials")
            resp.read()
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise AatControlError("AAT web login failed: invalid credentials") from error
        raise AatControlError(f"AAT login HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AatControlError(f"AAT unreachable: {error.reason}") from error

    action = "on" if on else "off"
    cmd_body = urllib.parse.urlencode({"rfControl": action}).encode("utf-8")
    try:
        cmd_req = urllib.request.Request(
            f"{base}/includes/3K_FM_Controller.php",
            data=cmd_body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with opener.open(cmd_req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as error:
        raise AatControlError(f"AAT control HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise AatControlError(f"AAT control failed: {error.reason}") from error

    lowered = text.lower()
    if lowered.startswith("<!doctype") or lowered.startswith("<html"):
        raise AatControlError(
            "AAT web interface did not accept the RF control command"
        )
    return text or f"AAT RF {action} command sent"
