"""GatesAir Flexiva FAX HTTP client.

Telemetry is available unauthenticated via GET /json (same payload the GUI
uses). Optional MD5 login (GET /key then GET /login?seed=…) is supported when
credentials are configured, but not required for read-only polling.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import AlarmState, MeterReading, TransmitterConfig, TransmitterReading, utc_now

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0

# Datapoints mapped into the shared TransmitterReading fields / meter list.
# scale: divide raw value by this (1 = already engineered units).
METER_SPECS: tuple[tuple[str, str, str, str, str, float], ...] = (
    # key, datapoint, label, unit, category, scale
    ("fwd_pwr_w", "tx.forward_power", "Forward power", "W", "rf", 1.0),
    ("rfl_pwr_w", "tx.reflected_pwr", "Reflected power", "W", "rf", 1.0),
    ("vswr", "tx.vswr", "VSWR", "", "rf", 1.0),
    ("frequency_mhz", "tx.cfg.frequency", "Frequency", "MHz", "rf", 1.0),
    ("tpo_set_w", "tx.cfg.tx_tpo_w", "TPO setpoint", "W", "rf", 1.0),
    ("peak_deviation_khz", "fax_lp.meter.peak_deviation", "Peak deviation", "kHz", "rf", 1000.0),
    ("pa_volts_v", "tx.pa_ave_volts", "PA average volts", "V", "pa", 1.0),
    ("pa_sum_current_a", "tx.pa_sum_current", "PA sum current", "A", "pa", 1.0),
    ("pa1_current_a", "fax_lp.meter.pa_i[0]", "PA 1 current", "A", "pa", 1000.0),
    ("pa2_current_a", "fax_lp.meter.pa_i[1]", "PA 2 current", "A", "pa", 1000.0),
    ("pa1_temp_c", "fax_lp.meter.pa_temp[0]", "PA 1 temperature", "°C", "pa", 1000.0),
    ("pa2_temp_c", "fax_lp.meter.pa_temp[1]", "PA 2 temperature", "°C", "pa", 1000.0),
    ("ipa_power_w", "tx.ipa_power", "IPA power", "W", "pa", 1.0),
    ("ipa_current_a", "fax_lp.meter.ipa_i", "IPA current", "A", "pa", 1000.0),
    ("ipa_temp_c", "fax_lp.meter.ipa_temp", "IPA temperature", "°C", "pa", 1000.0),
    ("external_drive_w", "tx.external_drive", "External drive", "W", "pa", 1.0),
    ("front_temp_c", "tx.front_temp", "Front temperature", "°C", "cooling", 1.0),
    ("board_temp_c", "board.temp", "Board temperature", "°C", "cooling", 1.0),
    ("rear_temp_c", "tx.rear_temp", "Rear temperature", "°C", "cooling", 1.0),
    ("fan1_rpm", "fax_lp.stat.fan1_tach", "Fan 1", "rpm", "cooling", 1.0),
    ("fan2_rpm", "fax_lp.stat.fan2_tach", "Fan 2", "rpm", "cooling", 1.0),
    ("ps_48v", "fax_lp.stat.ps1.voltage", "PS DC voltage", "V", "supply", 1000.0),
    ("ps_dc_current_a", "fax_lp.stat.ps1.current", "PS DC current", "A", "supply", 1000.0),
    ("ps_ac_volts", "fax_lp.stat.ps1.ac_volts", "PS AC volts", "V", "supply", 1000.0),
    ("ps_ac_current_a", "fax_lp.stat.ps1.ac_current", "PS AC current", "A", "supply", 1000.0),
    ("ps_temp_c", "fax_lp.stat.ps1.temp", "PS temperature", "°C", "supply", 1000.0),
    ("board_5v", "board.5vdc", "Board +5V", "V", "supply", 1.0),
    ("board_3v3", "board.3.3vdc", "Board +3.3V", "V", "supply", 1.0),
    ("board_1v4", "board.1_4vdc", "Board +1.4V", "V", "supply", 1.0),
    ("board_battery_v", "board.v_battery", "Board battery", "V", "supply", 1.0),
    ("tx_on", "tx.tx_on", "TX on", "", "control", 1.0),
    ("remote_enable", "tx.cfg.remote_enable", "Remote enable", "", "control", 1.0),
    ("interlock", "tx.interlock", "Interlock", "", "control", 1.0),
    ("rf_mute", "tx.rf_mute", "RF mute", "", "control", 1.0),
    ("ac_mains", "tx.ac_mains", "AC mains fault", "", "control", 1.0),
)

ALARM_SPECS: tuple[tuple[str, str, str], ...] = (
    # key, datapoint, label
    ("vswr_fault", "tx.vswr.fault", "VSWR fault"),
    ("sw_vswr_fault", "tx.sw_vswr.fault", "Software VSWR fault"),
    ("vswr_foldback", "tx.vswr_foldback", "VSWR foldback"),
    ("power_low", "tx.power_low_flt", "Power low"),
    ("power_limit", "tx.power_limit_flt", "Power limit"),
    ("pa_cable", "tx.pa_cable_fault", "PA cable fault"),
    ("fan_flt", "tx.fan_flt", "Fan fault"),
    ("airflow_flt", "tx.airflow_flt", "Airflow fault"),
    ("low_airflow", "tx.low_airflow_wrn", "Low airflow warning"),
    ("interlock", "tx.interlock", "Interlock open"),
    ("equip_intlk", "tx.equip_intlk", "Equipment interlock"),
    ("ac_mains", "tx.ac_mains", "AC mains fault"),
    ("rf_mute", "tx.rf_mute", "RF mute"),
    ("rej_load", "tx.rej_load_flt", "Reject load fault"),
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


def set_flexiva_rf(
    tx: TransmitterConfig, *, on: bool, timeout: float = DEFAULT_TIMEOUT
) -> str:
    """Experimental Flexiva RF write via GUI login + /wssajax datapoint set.

    Live validation is required before production use. Tries common FAX write
    encodings; raises FlexivaError with a clear message if the unit rejects them.
    """
    username = (tx.http_username or "gates").strip()
    password = tx.http_password or ""
    if not password:
        raise FlexivaError(
            "Flexiva RF control needs http_username/http_password in transmitter config"
        )

    base = _base_url(tx.host, tx.http_port)
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        key = (
            opener.open(f"{base}/key", timeout=timeout)
            .read()
            .decode("utf-8", errors="replace")
            .strip()
        )
    except Exception as error:
        raise FlexivaError(f"Flexiva /key failed: {error}") from error
    if not key:
        raise FlexivaError("Empty Flexiva /key response")

    seed = hashlib.md5((key + username.upper() + password).encode("utf-8")).hexdigest()
    try:
        login_resp = opener.open(f"{base}/login?seed={seed}", timeout=timeout)
        login_body = login_resp.read().decode("utf-8", errors="replace")
    except Exception as error:
        raise FlexivaError(f"Flexiva login failed: {error}") from error
    try:
        login_json = json.loads(login_body)
    except json.JSONDecodeError:
        login_json = {}
    if isinstance(login_json, dict) and login_json.get("response") not in (
        None,
        "accepted",
        "ok",
        "OK",
    ):
        if login_json.get("response") and login_json.get("response") != "accepted":
            raise FlexivaError(f"Flexiva login denied: {login_json}")

    value = "1" if on else "0"
    # Experimental encodings observed / inferred from FAX GUI (secCom / dpUpdate).
    attempts: list[tuple[str, bytes, dict[str, str]]] = [
        (
            "json-dps",
            json.dumps({"cmd": "set", "dps": {"tx.tx_on": int(value)}}).encode("utf-8"),
            {"Content-Type": "application/json", "Accept": "application/json"},
        ),
        (
            "json-cfg",
            json.dumps({"cmd": "set", "dps": {"tx.cfg.tx_on": int(value)}}).encode(
                "utf-8"
            ),
            {"Content-Type": "application/json", "Accept": "application/json"},
        ),
        (
            "form",
            urllib.parse.urlencode(
                {"cmd": "set", "name": "tx.tx_on", "value": value}
            ).encode("utf-8"),
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        ),
    ]

    errors: list[str] = []
    for label, body, headers in attempts:
        req = urllib.request.Request(
            f"{base}/wssajax",
            data=body,
            method="POST",
            headers=headers,
        )
        try:
            with opener.open(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace").strip()
            lowered = text.lower()
            if "error" in lowered and "ok" not in lowered:
                errors.append(f"{label}: {text[:160]}")
                continue
            # Accept empty/JSON ack as provisional success — live validate later.
            return (
                f"Flexiva RF {'ON' if on else 'OFF'} write sent via /wssajax ({label}). "
                "Experimental — confirm on the transmitter GUI before relying on this."
            )
        except Exception as error:
            errors.append(f"{label}: {error}")

    raise FlexivaError(
        "Flexiva RF write needs live validation — /wssajax set encodings were rejected. "
        + "; ".join(errors[:3])
    )


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
    for key, datapoint, label, unit, category, scale in METER_SPECS:
        raw = data.get(datapoint)
        parsed = _parse_float(raw)
        value: float | int | None = None
        if parsed is not None:
            scaled = parsed / scale if scale and scale != 1.0 else parsed
            if key in (
                "tx_on",
                "remote_enable",
                "interlock",
                "rf_mute",
                "ac_mains",
                "fan1_rpm",
                "fan2_rpm",
            ):
                value = int(round(scaled))
            else:
                value = scaled
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
    pa1_temp = _as_float(values.get("pa1_temp_c"))
    heatsink = pa1_temp if pa1_temp is not None else (
        front_temp if front_temp is not None else board_temp
    )
    remote = _parse_int(values.get("remote_enable"))

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
        pa_volts_v=_as_float(values.get("pa_volts_v")),
        pa_current_1_a=_as_float(values.get("pa1_current_a")),
        ipa_current_a=_as_float(values.get("ipa_current_a")),
        plus48_v=_as_float(values.get("ps_48v")),
        plus5_v=_as_float(values.get("board_5v")),
        fan1_rpm=_parse_int(values.get("fan1_rpm")),
        fan2_rpm=_parse_int(values.get("fan2_rpm")),
        rf_state=tx_on,
        local_remote=remote,
        meters=meters,
        alarms=alarms,
        oid_ok=ok,
        oid_total=total,
    )


def _as_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)
