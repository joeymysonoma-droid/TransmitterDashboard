"""Shared data models for ASMG TX monitoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


RF_STATE_LABELS = {0: "OFF", 1: "ON", 2: "INHIBITED"}
LOCAL_REMOTE_LABELS = {0: "LOCAL", 1: "REMOTE"}
NA_SENTINEL = -2147483648
FLEXIVA_MODELS = frozenset({"flexiva", "fax", "fax1k", "gatesair"})
AAT_MODELS = frozenset({"aat", "aat_fm", "american_amplifier"})
CROWN_MODELS = frozenset({"crown", "ecreso", "fmngip", "audemat_fm"})
HDLINK_MODELS = frozenset({"hdlink", "hd-link", "hd_link"})
IPLINK_MODELS = frozenset({"iplink", "ip-link", "ip_link"})
COMREX_MODELS = frozenset({"comrex", "access", "comrex-access"})
BRICLINK_MODELS = frozenset(
    {"briclink", "bric-link", "bric", "bric2", "bric-2", "brixlink"}
)
INSTREAM_MODELS = frozenset(
    {"instream", "instreamer", "instreamers", "sitestreamer", "inovonics", "635"}
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_flexiva_model(model: str) -> bool:
    return model.lower().strip() in FLEXIVA_MODELS


def is_aat_model(model: str) -> bool:
    return model.lower().strip() in AAT_MODELS


def is_crown_model(model: str) -> bool:
    return model.lower().strip() in CROWN_MODELS


def is_hdlink_model(model: str) -> bool:
    return model.lower().strip() in HDLINK_MODELS


def is_iplink_model(model: str) -> bool:
    return model.lower().strip() in IPLINK_MODELS


def is_comrex_model(model: str) -> bool:
    return model.lower().strip() in COMREX_MODELS


def is_briclink_model(model: str) -> bool:
    return model.lower().strip() in BRICLINK_MODELS


def is_instream_model(model: str) -> bool:
    return model.lower().strip() in INSTREAM_MODELS


def is_stl_model(model: str) -> bool:
    return (
        is_hdlink_model(model)
        or is_iplink_model(model)
        or is_comrex_model(model)
        or is_briclink_model(model)
        or is_instream_model(model)
    )


@dataclass
class TransmitterConfig:
    id: str
    name: str
    model: str  # vs300 | vx | flexiva | aat | crown
    host: str
    snmp_community: str = "public"
    snmp_port: int = 161
    http_port: int = 80
    http_username: str = ""
    http_password: str = ""
    location: str = ""
    # Optional per-TX alert overrides. Present keys replace global alerts.*;
    # explicit null disables a threshold for this TX only.
    alert_overrides: dict[str, Any] = field(default_factory=dict)
    # Per-TX RF control overrides (None = inherit global).
    controls_enabled: bool | None = None
    controls_password: str = ""
    snmp_write_community: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.host and self.host.strip())

    @property
    def is_flexiva(self) -> bool:
        return is_flexiva_model(self.model)

    @property
    def is_aat(self) -> bool:
        return is_aat_model(self.model)

    @property
    def is_crown(self) -> bool:
        return is_crown_model(self.model)

    @property
    def write_community(self) -> str:
        return (self.snmp_write_community or self.snmp_community or "public").strip()


@dataclass
class AlertConfig:
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True
    email_from: str = ""
    email_to: tuple[str, ...] = ()
    cooldown_minutes: int = 30
    unreachable_polls: int = 3
    on_unreachable: bool = True
    on_rf_off: bool = True
    on_tx_alarms: bool = True
    vswr: float | None = 1.5
    reflected_w: float | None = None
    heatsink_c: float | None = 70.0
    forward_min_w: float | None = None
    # Do not alert for hosts that are intentionally blank.
    skip_unconfigured: bool = True


@dataclass
class ControlsConfig:
    """RF control gating. Default off — enable explicitly before use."""

    enabled: bool = False
    password: str = ""


@dataclass
class StlDeviceConfig:
    """Link or codec. Not a transmitter and not stored as a TransmitterReading."""

    id: str
    name: str
    model: str  # hdlink | iplink | comrex | briclink | instream
    host: str
    snmp_community: str = "public"
    snmp_port: int = 161
    location: str = ""
    alert_overrides: dict[str, Any] = field(default_factory=dict)
    related_tx_id: str = ""
    # Comrex ACCESS and BRIC-Link web password. Masked like other secrets.
    http_password: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.host and self.host.strip())

    @property
    def is_hdlink(self) -> bool:
        return is_hdlink_model(self.model)

    @property
    def is_iplink(self) -> bool:
        return is_iplink_model(self.model)


@dataclass
class AppConfig:
    transmitters: list[TransmitterConfig]
    stl_devices: list[StlDeviceConfig] = field(default_factory=list)
    poll_interval_seconds: int = 30
    history_retention_days: int = 90
    history_min_interval_seconds: int = 60
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    snmp_timeout_seconds: float = 5.0
    snmp_retries: int = 2
    alerts: AlertConfig = field(default_factory=AlertConfig)
    controls: ControlsConfig = field(default_factory=ControlsConfig)


@dataclass
class AlarmState:
    key: str
    label: str
    active: bool


@dataclass
class MeterReading:
    key: str
    label: str
    value: float | int | None
    unit: str
    category: str


@dataclass
class TransmitterReading:
    tx_id: str
    timestamp: datetime
    status: str  # online | degraded | offline
    host: str
    name: str
    model: str
    location: str = ""
    fwd_pwr_w: float | None = None
    rfl_pwr_w: float | None = None
    vswr: float | None = None
    heatsink_temp_c: float | None = None
    pa_volts_v: float | None = None
    pa_current_1_a: float | None = None
    ipa_current_a: float | None = None
    plus48_v: float | None = None
    plus15_v: float | None = None
    minus15_v: float | None = None
    plus5_v: float | None = None
    fan1_rpm: int | None = None
    fan2_rpm: int | None = None
    rf_state: int | None = None
    local_remote: int | None = None
    meters: list[MeterReading] = field(default_factory=list)
    alarms: list[AlarmState] = field(default_factory=list)
    error: str | None = None
    oid_ok: int = 0
    oid_total: int = 0

    @property
    def rf_state_label(self) -> str:
        if self.rf_state is None:
            return "—"
        return RF_STATE_LABELS.get(self.rf_state, str(self.rf_state))

    @property
    def local_remote_label(self) -> str:
        if self.local_remote is None:
            return "—"
        return LOCAL_REMOTE_LABELS.get(self.local_remote, str(self.local_remote))

    @property
    def active_alarm_count(self) -> int:
        return sum(1 for a in self.alarms if a.active)

    def summary_lines(self) -> list[str]:
        return [
            f"Status: {self.status}",
            f"RF: {self.rf_state_label}",
            f"Forward: {self.fwd_pwr_w if self.fwd_pwr_w is not None else '—'} W",
            f"Reflected: {self.rfl_pwr_w if self.rfl_pwr_w is not None else '—'} W",
            f"VSWR: {self.vswr if self.vswr is not None else '—'}",
            f"Heatsink: {self.heatsink_temp_c if self.heatsink_temp_c is not None else '—'} C",
            f"Active alarms: {self.active_alarm_count}",
        ]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["rf_state_label"] = self.rf_state_label
        data["local_remote_label"] = self.local_remote_label
        data["active_alarm_count"] = self.active_alarm_count
        # VS Legacy AUI needs Java; VX / Flexiva expose HTML UIs.
        model = self.model.lower()
        if not self.host:
            data["aui_url"] = None
            data["aui_label"] = None
        elif is_flexiva_model(model):
            data["aui_url"] = f"http://{self.host}/fax/html/index.html"
            data["aui_label"] = "Open GUI"
        elif is_aat_model(model):
            data["aui_url"] = f"http://{self.host}"
            data["aui_label"] = "Open GUI"
        elif is_crown_model(model):
            data["aui_url"] = f"http://{self.host}"
            data["aui_label"] = "Open GUI"
        elif model.startswith("vs"):
            data["aui_url"] = None
            data["aui_label"] = None
        else:
            data["aui_url"] = f"http://{self.host}"
            data["aui_label"] = "Open AUI"
        return data


def stl_model_label(model: str) -> str:
    if is_hdlink_model(model):
        return "HD Link"
    if is_iplink_model(model):
        return "IP Link"
    if is_comrex_model(model):
        return "Comrex"
    if is_briclink_model(model):
        return "BRIC-Link"
    if is_instream_model(model):
        return "Instream"
    return model or "STL"


@dataclass
class StlReading:
    """One STL poll. No forward power, VSWR, or RF-on fields."""

    stl_id: str
    timestamp: datetime
    reachable: bool
    status: str  # online | degraded | offline
    host: str
    name: str
    model: str
    location: str = ""
    link_state: str = "unknown"  # up | down | degraded | unknown
    link_label: str = ""
    meters: list[MeterReading] = field(default_factory=list)
    alarms: list[AlarmState] = field(default_factory=list)
    error: str | None = None
    oid_ok: int = 0
    oid_total: int = 0
    related_tx_id: str = ""

    @property
    def active_alarm_count(self) -> int:
        return sum(1 for alarm in self.alarms if alarm.active)

    def summary_lines(self) -> list[str]:
        meter_bits = [
            f"{meter.label}: {meter.value if meter.value is not None else '—'} {meter.unit}".rstrip()
            for meter in self.meters[:4]
        ]
        return [
            f"Status: {self.status}",
            f"Link: {self.link_label or self.link_state}",
            *meter_bits,
            f"Active alarms: {self.active_alarm_count}",
        ]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["active_alarm_count"] = self.active_alarm_count
        data["model_label"] = stl_model_label(self.model)
        if self.host:
            data["gui_url"] = f"http://{self.host}"
        else:
            data["gui_url"] = None
        return data
