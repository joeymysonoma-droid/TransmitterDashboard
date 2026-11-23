"""Read-only SNMPv2c polls for Intraplex HD Link and IP Link."""

from __future__ import annotations

import logging

from .models import (
    AlarmState,
    MeterReading,
    StlDeviceConfig,
    StlReading,
    is_briclink_model,
    is_comrex_model,
    is_hdlink_model,
    is_iplink_model,
    is_instream_model,
    utc_now,
)
from .snmp_client import SnmpError, snmp_get, snmp_getnext
from .stl_oids import (
    HD_LOCK_UP,
    HD_SCALARS,
    IP_CONNECTED_COLUMN,
    IP_ENABLED_COLUMN,
    IP_METER_COLUMNS,
    IP_NAME_COLUMN,
    IP_STREAM_TABLE,
    IP_UPTIME_COLUMN,
    SYS_DESCR,
    SYS_NAME,
    StlScalar,
)

logger = logging.getLogger(__name__)


def poll_stl(
    device: StlDeviceConfig,
    *,
    timeout: float = 5.0,
    retries: int = 1,
) -> StlReading:
    if is_hdlink_model(device.model):
        return poll_hdlink(device, timeout=timeout, retries=retries)
    if is_iplink_model(device.model):
        return poll_iplink(device, timeout=timeout, retries=retries)
    if is_comrex_model(device.model) or is_briclink_model(device.model):
        from .codec_client import poll_comrex

        return poll_comrex(device, timeout=timeout, retries=retries)
    if is_instream_model(device.model):
        from .codec_client import poll_instream

        return poll_instream(device, timeout=timeout, retries=retries)
    return _offline(device, f"Unsupported STL model: {device.model}")


def poll_hdlink(
    device: StlDeviceConfig,
    *,
    timeout: float = 5.0,
    retries: int = 1,
) -> StlReading:
    if not device.configured:
        return _offline(device, "Host IP not configured", reachable=False)

    identity = _identity(device, timeout=timeout, retries=retries)
    if identity is None:
        return _offline(device, "SNMP unreachable")

    raw = _get_many(
        device,
        [item.oid for item in HD_SCALARS],
        timeout=timeout,
        retries=retries,
    )
    meters: list[MeterReading] = []
    alarms: list[AlarmState] = []
    oid_ok = 0
    oid_total = 0
    lock_value: int | None = None
    alarm_count: int | None = None
    role = ""

    for item in HD_SCALARS:
        if item.key in {"rx_lock", "alarm_count", "role"}:
            if not item.optional:
                oid_total += 1
            parsed = _interpret(item, raw.get(item.oid))
            if parsed.present:
                oid_ok += 1
            if item.key == "rx_lock" and isinstance(parsed.number, int):
                lock_value = parsed.number
            elif item.key == "alarm_count" and isinstance(parsed.number, int):
                alarm_count = parsed.number
            elif item.key == "role" and parsed.text:
                role = parsed.text
            continue

        if not item.optional:
            oid_total += 1
        parsed = _interpret(item, raw.get(item.oid))
        if not parsed.present:
            if item.optional:
                continue
            meters.append(_meter(item, None))
            continue
        oid_ok += 1
        if item.key == "freq_hz" and isinstance(parsed.number, (int, float)):
            mhz = float(parsed.number) / 1_000_000.0
            meters.append(
                MeterReading(
                    key="freq_mhz",
                    label="Frequency",
                    value=round(mhz, 3),
                    unit="MHz",
                    category=item.category,
                )
            )
            continue
        meters.append(_meter(item, parsed.number))

    if lock_value in HD_LOCK_UP:
        link_state = "up"
        link_label = "Locked" if lock_value == 1 else "On path"
    elif lock_value == 0:
        link_state = "down"
        link_label = "Down"
    elif lock_value is None:
        link_state = "unknown"
        link_label = "Unknown"
    else:
        link_state = "down"
        link_label = f"Lock {lock_value}"
    if role:
        link_label = f"{link_label} · {role}"

    if link_state == "down":
        alarms.append(AlarmState(key="link_down", label="Link down", active=True))
    if alarm_count is not None and alarm_count > 0:
        alarms.append(
            AlarmState(
                key="alarm_count",
                label=f"{alarm_count} STL alarm{'s' if alarm_count != 1 else ''}",
                active=True,
            )
        )

    status = _status(oid_ok, oid_total, link_state, alarms)
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
        oid_ok=oid_ok,
        oid_total=oid_total,
        related_tx_id=device.related_tx_id,
        error=None if status != "degraded" else _partial_error(oid_ok, oid_total),
    )


def poll_iplink(
    device: StlDeviceConfig,
    *,
    timeout: float = 5.0,
    retries: int = 1,
) -> StlReading:
    if not device.configured:
        return _offline(device, "Host IP not configured", reachable=False)

    identity = _identity(device, timeout=timeout, retries=retries)
    if identity is None:
        return _offline(device, "SNMP unreachable")

    try:
        names = _walk_column(
            device,
            IP_NAME_COLUMN,
            timeout=timeout,
            retries=retries,
            limit=8,
        )
    except SnmpError as error:
        logger.warning("IP Link stream walk failed for %s: %s", device.id, error)
        return _reachable_down(device, f"Stream table unavailable: {error}")

    streams: list[dict[str, object]] = []
    for index, name in names:
        label = str(name).strip() if name is not None else ""
        if not label:
            continue
        columns = [IP_ENABLED_COLUMN, IP_CONNECTED_COLUMN, IP_UPTIME_COLUMN]
        columns.extend(col for col, *_rest in IP_METER_COLUMNS)
        oids = [f"{IP_STREAM_TABLE}.{col}.{index}" for col in columns]
        raw = _get_many(device, oids, timeout=timeout, retries=retries)
        row: dict[str, object] = {"index": index, "name": label}
        for col in columns:
            row[col] = raw.get(f"{IP_STREAM_TABLE}.{col}.{index}")
        streams.append(row)

    if not streams:
        return _reachable_down(device, "No streams in SNMP table")

    up = 0
    alarms: list[AlarmState] = []
    bitrate_total = 0.0
    bitrate_seen = False
    loss_max: float | None = None
    level_values: list[float] = []
    oid_ok = 1  # identity GET succeeded
    oid_total = 1

    for row in streams:
        connected = _as_int(row.get(IP_CONNECTED_COLUMN))
        enabled = _as_int(row.get(IP_ENABLED_COLUMN))
        is_up = connected == 1
        if is_up:
            up += 1
        elif enabled in (None, 1):
            alarms.append(
                AlarmState(
                    key=f"stream_{row['index']}",
                    label=f"{row['name']} down",
                    active=True,
                )
            )
        bitrate = _parse_number(row.get(104))
        if isinstance(bitrate, (int, float)) and is_up:
            bitrate_total += float(bitrate)
            bitrate_seen = True
        loss = _parse_number(row.get(135))
        if isinstance(loss, (int, float)):
            loss_max = loss if loss_max is None else max(loss_max, float(loss))
        level = _parse_number(row.get(138))
        if isinstance(level, (int, float)):
            level_values.append(float(level))

    total = len(streams)
    if up == total:
        link_state = "up"
    elif up == 0:
        link_state = "down"
    else:
        link_state = "degraded"
    link_label = f"{up}/{total} streams up"

    meters = [
        MeterReading(
            key="streams_up",
            label="Streams up",
            value=up,
            unit="",
            category="stream",
        )
    ]
    oid_total += 1
    oid_ok += 1
    if bitrate_seen:
        meters.append(
            MeterReading(
                key="bitrate_kbps",
                label="Bitrate",
                value=round(bitrate_total, 1),
                unit="kbps",
                category="stream",
            )
        )
        oid_ok += 1
    oid_total += 1
    if loss_max is not None:
        meters.append(
            MeterReading(
                key="packet_loss_pct",
                label="Loss",
                value=round(loss_max, 3),
                unit="%",
                category="error",
            )
        )
        oid_ok += 1
    oid_total += 1
    if level_values:
        meters.append(
            MeterReading(
                key="stream_level",
                label="Level",
                value=round(sum(level_values) / len(level_values), 2),
                unit="",
                category="stream",
            )
        )
        oid_ok += 1
    oid_total += 1

    if link_state == "down":
        alarms.append(AlarmState(key="link_down", label="Link down", active=True))

    status = _status(oid_ok, max(oid_total, 1), link_state, alarms)
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
        oid_ok=oid_ok,
        oid_total=oid_total,
        related_tx_id=device.related_tx_id,
    )


def _identity(
    device: StlDeviceConfig,
    *,
    timeout: float,
    retries: int,
) -> dict[str, int | str | None] | None:
    try:
        return snmp_get(
            device.host,
            device.snmp_community,
            [SYS_DESCR, SYS_NAME],
            port=device.snmp_port,
            timeout=timeout,
            retries=retries,
        )
    except SnmpError as error:
        logger.warning("SNMP failed for STL %s (%s): %s", device.id, device.host, error)
        return None


def _get_many(
    device: StlDeviceConfig,
    oids: list[str],
    *,
    timeout: float,
    retries: int,
) -> dict[str, int | str | None]:
    if not oids:
        return {}
    try:
        return snmp_get(
            device.host,
            device.snmp_community,
            oids,
            port=device.snmp_port,
            timeout=timeout,
            retries=retries,
        )
    except SnmpError:
        merged: dict[str, int | str | None] = {}
        for oid in oids:
            try:
                merged.update(
                    snmp_get(
                        device.host,
                        device.snmp_community,
                        [oid],
                        port=device.snmp_port,
                        timeout=timeout,
                        retries=0,
                    )
                )
            except SnmpError:
                continue
        return merged


def _walk_column(
    device: StlDeviceConfig,
    column: str,
    *,
    timeout: float,
    retries: int,
    limit: int,
) -> list[tuple[str, int | str | None]]:
    current = column
    found: list[tuple[str, int | str | None]] = []
    prefix = column + "."
    for _ in range(limit):
        try:
            nxt, value = snmp_getnext(
                device.host,
                device.snmp_community,
                current,
                port=device.snmp_port,
                timeout=timeout,
                retries=retries,
            )
        except SnmpError as error:
            if found and "end of mib" in str(error):
                break
            if not found:
                raise
            break
        if not nxt.startswith(prefix):
            break
        index = nxt[len(prefix) :]
        if "." in index:
            break
        found.append((index, value))
        current = nxt
    return found


class _Parsed:
    def __init__(self, present: bool, number: int | float | None, text: str) -> None:
        self.present = present
        self.number = number
        self.text = text


def _interpret(item: StlScalar, raw: int | str | None) -> _Parsed:
    if raw is None:
        return _Parsed(False, None, "")
    if isinstance(raw, str) and not raw.strip():
        return _Parsed(False, None, "")
    number = _parse_number(raw)
    text = raw.strip() if isinstance(raw, str) else ""
    if number is None and not text:
        return _Parsed(False, None, "")
    return _Parsed(True, number, text)


def _meter(item: StlScalar, value: int | float | None) -> MeterReading:
    return MeterReading(
        key=item.key,
        label=item.label,
        value=value,
        unit=item.unit,
        category=item.category,
    )


def _parse_number(value: object) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"not available", "unknown"}:
            return None
        try:
            if any(ch in text for ch in ".eE"):
                return float(text)
            return int(text)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    number = _parse_number(value)
    if isinstance(number, bool) or number is None:
        return None
    return int(number)


def _status(
    oid_ok: int,
    oid_total: int,
    link_state: str,
    alarms: list[AlarmState],
) -> str:
    if oid_total and oid_ok == 0:
        return "offline"
    if link_state in {"down", "degraded", "unknown"}:
        return "degraded"
    if any(alarm.active for alarm in alarms):
        return "degraded"
    if oid_ok < oid_total:
        return "degraded"
    return "online"


def _partial_error(oid_ok: int, oid_total: int) -> str | None:
    if oid_total and oid_ok < oid_total:
        return f"{oid_ok}/{oid_total} OIDs answered"
    return None


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


def _reachable_down(device: StlDeviceConfig, error: str) -> StlReading:
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
        alarms=[AlarmState(key="link_down", label="Link state unknown", active=True)],
    )
