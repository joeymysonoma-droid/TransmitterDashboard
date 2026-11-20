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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_flexiva_model(model: str) -> bool:
    return model.lower().strip() in FLEXIVA_MODELS


def is_aat_model(model: str) -> bool:
    return model.lower().strip() in AAT_MODELS


def is_crown_model(model: str) -> bool:
    return model.lower().strip() in CROWN_MODELS


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
class AppConfig:
    transmitters: list[TransmitterConfig]
    poll_interval_seconds: int = 30
    history_retention_days: int = 90
    history_min_interval_seconds: int = 60
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    snmp_timeout_seconds: float = 5.0
    snmp_retries: int = 2
    alerts: AlertConfig = field(default_factory=AlertConfig)


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
