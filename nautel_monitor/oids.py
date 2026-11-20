"""Curated SNMP OID maps from Nautel VS and VX MIBs.

VS: NAUTEL-VS_SW_5.2-MIB  (enterprise 28142, products 300, controller 256)
VX: NAUTEL-VX-7.1.0-MIB   (nautel 753915, objects 1, controller 365761128)

Meter integers use Tenths/Hundredths/Thousandths textual conventions.
A raw value of -2147483648 means N/A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import NA_SENTINEL


VS_CONTROLLER = "1.3.6.1.4.1.28142.1.300.256"
VX_CONTROLLER = "1.3.6.1.4.1.28142.753915.1.365761128"


def _scale(divisor: float) -> Callable[[int], float | None]:
    def convert(raw: int) -> float | None:
        if raw == NA_SENTINEL:
            return None
        return raw / divisor

    return convert


def _identity(raw: int) -> int | None:
    if raw == NA_SENTINEL:
        return None
    return raw


@dataclass(frozen=True)
class MeterOid:
    key: str
    oid: str
    label: str
    unit: str
    category: str  # rf | pa | supply | cooling | control
    convert: Callable[[int], float | int | None]


@dataclass(frozen=True)
class AlarmOid:
    key: str
    oid: str
    label: str


def _oid(base: str, leaf: int) -> str:
    return f"{base}.{leaf}.0"


VS_METERS: list[MeterOid] = [
    MeterOid("fwd_pwr_w", _oid(VS_CONTROLLER, 256), "Forward Power", "W", "rf", _scale(1000)),
    MeterOid("rfl_pwr_w", _oid(VS_CONTROLLER, 257), "Reflected Power", "W", "rf", _scale(1000)),
    MeterOid("vswr", _oid(VS_CONTROLLER, 303), "VSWR", "", "rf", _scale(1000)),
    MeterOid("heatsink_temp_c", _oid(VS_CONTROLLER, 271), "Heatsink Temp 1", "°C", "cooling", _scale(1000)),
    MeterOid("heatsink_temp2_c", _oid(VS_CONTROLLER, 272), "Heatsink Temp 2", "°C", "cooling", _scale(1000)),
    MeterOid("pa_volts_v", _oid(VS_CONTROLLER, 259), "PA Volts A", "V", "pa", _scale(1000)),
    MeterOid("preamp_current_a", _oid(VS_CONTROLLER, 261), "Preamp Current", "A", "pa", _scale(1000)),
    MeterOid("ipa_current_a", _oid(VS_CONTROLLER, 262), "IPA Current", "A", "pa", _scale(1000)),
    MeterOid("pa_current_1_a", _oid(VS_CONTROLLER, 263), "PA 1 Current", "A", "pa", _scale(1000)),
    MeterOid("pa_current_2_a", _oid(VS_CONTROLLER, 264), "PA 2 Current", "A", "pa", _scale(1000)),
    MeterOid("pa_current_3_a", _oid(VS_CONTROLLER, 265), "PA 3 Current", "A", "pa", _scale(1000)),
    MeterOid("pa_current_4_a", _oid(VS_CONTROLLER, 266), "PA 4 Current", "A", "pa", _scale(1000)),
    MeterOid("plus48_v", _oid(VS_CONTROLLER, 273), "LVPS Input (+48V)", "V", "supply", _scale(1000)),
    MeterOid("plus15_v", _oid(VS_CONTROLLER, 274), "+15V", "V", "supply", _scale(1000)),
    MeterOid("minus15_v", _oid(VS_CONTROLLER, 275), "-15V", "V", "supply", _scale(1000)),
    MeterOid("plus5_v", _oid(VS_CONTROLLER, 276), "+5V", "V", "supply", _scale(1000)),
    MeterOid("plus3_3_v", _oid(VS_CONTROLLER, 277), "+3.3V", "V", "supply", _scale(1000)),
    MeterOid("battery_v", _oid(VS_CONTROLLER, 280), "Battery Voltage", "V", "supply", _scale(1000)),
    MeterOid("fan1_rpm", _oid(VS_CONTROLLER, 281), "Fan 1", "rpm", "cooling", _identity),
    MeterOid("fan2_rpm", _oid(VS_CONTROLLER, 282), "Fan 2", "rpm", "cooling", _identity),
    MeterOid("fan3_rpm", _oid(VS_CONTROLLER, 283), "Fan 3", "rpm", "cooling", _identity),
    MeterOid("fan4_rpm", _oid(VS_CONTROLLER, 284), "Fan 4", "rpm", "cooling", _identity),
    MeterOid("fan5_rpm", _oid(VS_CONTROLLER, 285), "Fan 5", "rpm", "cooling", _identity),
    MeterOid("rf_state", _oid(VS_CONTROLLER, 35), "RF State", "", "control", _identity),
    MeterOid("local_remote", _oid(VS_CONTROLLER, 8), "Local/Remote", "", "control", _identity),
]

VS_ALARMS: list[AlarmOid] = [
    AlarmOid("tx_rf_off", _oid(VS_CONTROLLER, 1536), "Transmitter RF Off"),
    AlarmOid("ext_interlock", _oid(VS_CONTROLLER, 1537), "External Interlock Open"),
    AlarmOid("pa_over_temp", _oid(VS_CONTROLLER, 1571), "PA Over Temperature"),
    AlarmOid("high_rfl", _oid(VS_CONTROLLER, 1588), "High Reflected Power"),
    AlarmOid("high_fwd", _oid(VS_CONTROLLER, 1596), "High Forward Power"),
    AlarmOid("fwd_low", _oid(VS_CONTROLLER, 1600), "Forward Power Low"),
    AlarmOid("fwd_low_low", _oid(VS_CONTROLLER, 1601), "Forward Power Very Low"),
]

VX_METERS: list[MeterOid] = [
    # RF
    MeterOid("fwd_pwr_w", _oid(VX_CONTROLLER, 265), "Forward Power", "W", "rf", _scale(1000)),
    MeterOid("rfl_pwr_w", _oid(VX_CONTROLLER, 257), "Reflected Power", "W", "rf", _scale(1000)),
    MeterOid("vswr", _oid(VX_CONTROLLER, 260), "VSWR", "", "rf", _scale(1000)),
    MeterOid("rf_drive_w", _oid(VX_CONTROLLER, 4352), "RF Drive Power", "W", "rf", _scale(1000)),
    MeterOid("dc_efficiency", _oid(VX_CONTROLLER, 262), "DC-RF Efficiency", "%", "rf", _scale(1000)),
    MeterOid("mod_peak", _oid(VX_CONTROLLER, 289), "Modulation Peak", "%", "rf", _scale(100)),
    MeterOid("mpx_rms", _oid(VX_CONTROLLER, 290), "MPX RMS", "%", "rf", _scale(100)),
    # PA / drive
    MeterOid("pa_volts_v", _oid(VX_CONTROLLER, 263), "Average PA Volts", "V", "pa", _scale(100)),
    MeterOid("pa_current_1_a", _oid(VX_CONTROLLER, 4354), "PA 1 Current", "A", "pa", _scale(1000)),
    MeterOid("pa1_volts_v", _oid(VX_CONTROLLER, 4353), "PA 1 Voltage", "V", "pa", _scale(100)),
    MeterOid("pa2_volts_v", _oid(VX_CONTROLLER, 4356), "PA 2 Voltage", "V", "pa", _scale(100)),
    MeterOid("pa_current_2_a", _oid(VX_CONTROLLER, 4357), "PA 2 Current", "A", "pa", _scale(1000)),
    MeterOid("total_pa_current_a", _oid(VX_CONTROLLER, 264), "Total PA Current", "A", "pa", _scale(1000)),
    MeterOid("ipa_current_a", _oid(VX_CONTROLLER, 4371), "IPA Current", "A", "pa", _scale(1000)),
    MeterOid("ipa_volts_v", _oid(VX_CONTROLLER, 4389), "IPA Voltage", "V", "pa", _scale(100)),
    MeterOid("pa1_dissipation_w", _oid(VX_CONTROLLER, 320), "PA 1 Dissipation", "W", "pa", _scale(1000)),
    MeterOid("pa2_dissipation_w", _oid(VX_CONTROLLER, 321), "PA 2 Dissipation", "W", "pa", _scale(1000)),
    # Supplies
    MeterOid("ps_a_input_v", _oid(VX_CONTROLLER, 4381), "PS A Input", "V", "supply", _scale(100)),
    MeterOid("plus12_v", _oid(VX_CONTROLLER, 276), "+12V", "V", "supply", _scale(1000)),
    MeterOid("plus5_v", _oid(VX_CONTROLLER, 277), "+5V", "V", "supply", _scale(1000)),
    MeterOid("plus3_3_v", _oid(VX_CONTROLLER, 272), "+3.3V", "V", "supply", _scale(1000)),
    MeterOid("plus2_5_v", _oid(VX_CONTROLLER, 274), "+2.5V", "V", "supply", _scale(1000)),
    MeterOid("plus1_5_v", _oid(VX_CONTROLLER, 275), "+1.5V", "V", "supply", _scale(1000)),
    MeterOid("plus1_1_v", _oid(VX_CONTROLLER, 273), "+1.1V", "V", "supply", _scale(1000)),
    # Cooling / control
    MeterOid("heatsink_temp_c", _oid(VX_CONTROLLER, 4704), "Heatsink Temp", "°C", "cooling", _scale(10)),
    MeterOid("rf_state", _oid(VX_CONTROLLER, 514), "RF State", "", "control", _identity),
    MeterOid("local_remote", _oid(VX_CONTROLLER, 8), "Local/Remote", "", "control", _identity),
]

VX_ALARMS: list[AlarmOid] = [
    AlarmOid("summary_fault", _oid(VX_CONTROLLER, 1280), "Summary Fault"),
    AlarmOid("summary_rf_output", _oid(VX_CONTROLLER, 1282), "Summary RF Output Fault"),
    AlarmOid("ext_interlock", _oid(VX_CONTROLLER, 1298), "External Interlock"),
    AlarmOid("dc_voltage_fail", _oid(VX_CONTROLLER, 1308), "DC Voltage Fail"),
    AlarmOid("plus12_fail", _oid(VX_CONTROLLER, 1307), "+12V Fail"),
    AlarmOid("high_fwd", _oid(VX_CONTROLLER, 1311), "High Forward Power"),
    AlarmOid("low_fwd", _oid(VX_CONTROLLER, 1312), "Low Forward Power"),
    AlarmOid("very_low_fwd", _oid(VX_CONTROLLER, 1313), "Very Low Forward Power"),
    AlarmOid("high_swr_shutdown", _oid(VX_CONTROLLER, 1314), "High SWR Shutdown"),
    AlarmOid("high_swr", _oid(VX_CONTROLLER, 1322), "High SWR"),
    AlarmOid("heatsink_warn", _oid(VX_CONTROLLER, 1325), "High Heatsink Temp Warning"),
    AlarmOid("heatsink_shutdown", _oid(VX_CONTROLLER, 1326), "High Heatsink Temp Shutdown"),
    AlarmOid("fan_fail_shutback", _oid(VX_CONTROLLER, 1396), "Fan Fail Shutback"),
    AlarmOid("low_ac_shutback", _oid(VX_CONTROLLER, 1346), "Low AC Shutback"),
]

PROFILES: dict[str, tuple[list[MeterOid], list[AlarmOid]]] = {
    "vs300": (VS_METERS, VS_ALARMS),
    "vx": (VX_METERS, VX_ALARMS),
}

CATEGORY_LABELS = {
    "rf": "RF",
    "pa": "PA / Drive",
    "supply": "Supplies",
    "cooling": "Cooling",
    "control": "Control",
}


def profile_for(model: str) -> tuple[list[MeterOid], list[AlarmOid]]:
    key = model.strip().lower()
    if key.startswith("vs"):
        return PROFILES["vs300"]
    if key.startswith("vx"):
        return PROFILES["vx"]
    raise KeyError(f"Unknown transmitter model profile: {model}")


def all_oids(model: str) -> list[str]:
    meters, alarms = profile_for(model)
    return [m.oid for m in meters] + [a.oid for a in alarms]
