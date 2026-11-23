"""Curated SNMPv2c OIDs for Intraplex HD Link and IP Link.

Enterprise 1.3.6.1.4.1.290 is the Intraplex tree (sysObjectID
1.3.6.1.4.1.290.7.1.1.0 on both families). GatesAir Flexiva transmitters
use 1.3.6.1.4.1.43768 — that tree is not valid for HD Link or IP Link.

Names below were checked with read-only GETs against HD Link firmware
V2.4.1 and IP Link 200 firmware V3.2.3. Vendor MIB text, when downloaded
from intraplex.org, belongs in mibs/. Scalar layouts can move between
firmware builds; confirm with scripts/probe_stl_snmp.py before trusting
a new release.

HD Link radio scalars live under
1.3.6.1.4.1.290.7.1.1.1.6.3.1.1.2.*
Observed on a receiver with a locked path: bandwidth 500 (matches the
loaded 500 kHz profile), constellation 256, SNR near 28, receive level
a negative dBm reading, and .2.7.0 = 1. The same .2.7.0 object read 2
on a transmitting HD Link. 0 is treated as path down.

IP Link stream rows are indexed under
1.3.6.1.4.1.290.7.1.1.1.8.6.1.3.1.{column}.{index}
Column 104 tracks stream rate in kbps, 123 is 1 while the stream is up,
135 is a loss percent, and 152 is an uptime string.
"""

from __future__ import annotations

from dataclasses import dataclass

# Not 1.3.6.1.4.1.43768 (Flexiva FM).
INTRAPLEX_ENTERPRISE = "1.3.6.1.4.1.290"
HD_ROOT = "1.3.6.1.4.1.290.7.1.1.1.6"
IP_ROOT = "1.3.6.1.4.1.290.7.1.1.1.8"

HD_RADIO = f"{HD_ROOT}.3.1.1.2"
HD_ALARM_COUNT = f"{HD_ROOT}.3.1.1.1.3.0"
HD_ROLE = f"{HD_ROOT}.3.1.2.1.12.1"
HD_FREQ_HZ = f"{HD_ROOT}.3.1.2.1.2.1"

IP_STREAM_TABLE = f"{IP_ROOT}.6.1.3.1"
IP_NAME_COLUMN = f"{IP_STREAM_TABLE}.2"

SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"

# .2.7.0 on HD Link. 1 = receiver locked, 2 = transmitter on path, 0 = down.
HD_LOCK_UP = frozenset({1, 2})


@dataclass(frozen=True)
class StlScalar:
    key: str
    label: str
    oid: str
    unit: str
    category: str
    on_card: bool = False
    optional: bool = False


HD_SCALARS: tuple[StlScalar, ...] = (
    StlScalar("snr_db", "SNR", f"{HD_RADIO}.6.0", "dB", "signal", on_card=True),
    StlScalar("rx_level_dbm", "Rx level", f"{HD_RADIO}.4.0", "dBm", "signal", on_card=True),
    StlScalar("wb_level_dbm", "WB level", f"{HD_RADIO}.8.0", "dBm", "signal", on_card=True),
    StlScalar("bandwidth_khz", "Bandwidth", f"{HD_RADIO}.1.0", "kHz", "signal", on_card=True),
    StlScalar("modulation", "QAM", f"{HD_RADIO}.2.0", "", "signal"),
    StlScalar(
        "error_rate",
        "Error rate",
        f"{HD_RADIO}.5.0",
        "",
        "error",
        optional=True,
    ),
    StlScalar("rx_lock", "Lock", f"{HD_RADIO}.7.0", "", "link"),
    StlScalar("alarm_count", "Alarm count", HD_ALARM_COUNT, "", "alarm"),
    StlScalar("role", "Radio", HD_ROLE, "", "link", optional=True),
    StlScalar("freq_hz", "Frequency", HD_FREQ_HZ, "Hz", "signal", optional=True),
)

# column number -> meter metadata. name/connected/uptime are handled apart.
IP_METER_COLUMNS: tuple[tuple[int, str, str, str, str, bool], ...] = (
    # col, key, label, unit, category, on_card
    (104, "bitrate_kbps", "Bitrate", "kbps", "stream", True),
    (135, "packet_loss_pct", "Loss", "%", "error", True),
    (138, "stream_level", "Level", "", "stream", True),
)
IP_ENABLED_COLUMN = 3
IP_CONNECTED_COLUMN = 123
IP_UPTIME_COLUMN = 152
