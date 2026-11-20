"""American Amplifier Technologies (AAT) FM TX SNMP client.

OID map from aat_FM_Tx_1_1.mib (enterprise 51550), matching AAT_Monitor.
VSWR is reported in hundredths; power/temps are already engineering units.
"""

from __future__ import annotations

import logging

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
