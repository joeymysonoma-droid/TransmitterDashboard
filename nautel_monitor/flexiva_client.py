"""GatesAir Flexiva FAX HTTP client.

Telemetry is available unauthenticated via GET /json (same payload the GUI
uses). Optional MD5 login (GET /key then GET /login?seed=…) is supported when
credentials are configured, but not required for read-only polling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from .models import AlarmState, MeterReading, TransmitterConfig, TransmitterReading, utc_now

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0

# Datapoints mapped into the shared TransmitterReading fields / meter list.
METER_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    # key, datapoint, label, unit, category
    ("fwd_pwr_w", "tx.forward_power", "Forward power", "W", "rf"),
    ("rfl_pwr_w", "tx.reflected_pwr", "Reflected power", "W", "rf"),
    ("vswr", "tx.vswr", "VSWR", "", "rf"),
    ("ipa_power_w", "tx.ipa_power", "IPA power", "W", "pa"),
    ("front_temp_c", "tx.front_temp", "Front temperature", "°C", "cooling"),
    ("board_temp_c", "board.temp", "Board temperature", "°C", "cooling"),
    ("tx_on", "tx.tx_on", "TX on", "", "control"),
)

ALARM_SPECS: tuple[tuple[str, str, str], ...] = (
    # key, datapoint, label
    ("vswr_fault", "tx.vswr.fault", "VSWR fault"),
    ("sw_vswr_fault", "tx.sw_vswr.fault", "Software VSWR fault"),
    ("power_low", "tx.power_low_flt", "Power low"),
    ("power_limit", "tx.power_limit_flt", "Power limit"),
    ("pa_cable", "tx.pa_cable_fault", "PA cable fault"),
    ("sys_temp", "fax_lp.flt.sys.temp", "System temperature fault"),
    ("sys_temp_foldback", "fax_lp.flt.sys.temp_fldbk", "Temp foldback fault"),
    ("power_loop", "fax_lp.flt.sys.power_loop", "Power loop fault"),
    ("lp_vswr", "fax_lp.flt.sw_vswr_fault", "LP VSWR fault"),
)


class FlexivaError(RuntimeError):
    pass


def _base_url(host: str, http_port: int = 80) -> str:
    host = host.strip()
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    if http_port and http_port != 80:
        return f"http://{host}:{http_port}"
    return f"http://{host}"


def _http_get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise FlexivaError(f"HTTP {error.code} from {url}") from error
    except urllib.error.URLError as error:
        raise FlexivaError(f"Unreachable: {error.reason}") from error
    except TimeoutError as error:
        raise FlexivaError("Request timed out") from error
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise FlexivaError("Invalid JSON from transmitter") from error


def login(host: str, username: str, password: str, http_port: int = 80) -> dict[str, Any]:
    """Optional MD5 challenge login used by the Flexiva GUI."""
    base = _base_url(host, http_port)
    key = (
        urllib.request.urlopen(f"{base}/key", timeout=DEFAULT_TIMEOUT)
        .read()
        .decode("utf-8", errors="replace")
        .strip()
    )
    if not key:
        raise FlexivaError("Empty /key response")
    seed = hashlib.md5((key + username.upper() + password).encode("utf-8")).hexdigest()
    result = _http_get_json(f"{base}/login?seed={seed}")
    if not isinstance(result, dict) or result.get("response") != "accepted":
        raise FlexivaError(f"Login denied: {result}")
    return result


def fetch_json(
    host: str,
    http_port: int = 80,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    data = _http_get_json(f"{_base_url(host, http_port)}/json", timeout=timeout)
    if not isinstance(data, dict):
        raise FlexivaError("Unexpected /json payload")
    return data


def _parse_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse_int(raw: Any) -> int | None:
    value = _parse_float(raw)
    if value is None:
        return None
    return int(value)


def _is_active(raw: Any) -> bool:
    value = _parse_float(raw)
    return value is not None and value != 0


def poll_flexiva(tx: TransmitterConfig, timeout: float = DEFAULT_TIMEOUT) -> TransmitterReading:
    """Poll one Flexiva transmitter and return a TransmitterReading."""
    try:
        data = fetch_json(tx.host, http_port=tx.http_port, timeout=timeout)
    except FlexivaError as error:
        logger.warning("Flexiva poll failed for %s (%s): %s", tx.id, tx.host, error)
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
    for key, datapoint, label, unit, category in METER_SPECS:
        raw = data.get(datapoint)
        if key in ("vswr", "front_temp_c", "board_temp_c", "ipa_power_w"):
            value: float | int | None = _parse_float(raw)
        elif key == "tx_on":
            value = _parse_int(raw)
        else:
            value = _parse_float(raw)
        if value is not None:
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
    for key, datapoint, label in ALARM_SPECS:
        raw = data.get(datapoint)
        present = raw is not None and raw != ""
        if present:
            ok += 1
        alarms.append(AlarmState(key=key, label=label, active=_is_active(raw)))

    total = len(METER_SPECS) + len(ALARM_SPECS)
    if ok == 0:
        status = "offline"
    elif ok < max(4, total // 4):
        status = "degraded"
    else:
        status = "online"

    tx_on = _parse_int(values.get("tx_on"))
    front_temp = _as_float(values.get("front_temp_c"))
    board_temp = _as_float(values.get("board_temp_c"))
    heatsink = front_temp if front_temp is not None else board_temp

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
        heatsink_temp_c=heatsink,
        rf_state=tx_on,
        meters=meters,
        alarms=alarms,
        oid_ok=ok,
        oid_total=total,
    )


def _as_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)
