"""Load transmitter dashboard configuration from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import AlertConfig, AppConfig, TransmitterConfig
from .paths import resolve_config_path

DEFAULT_CONFIG = resolve_config_path()


def _tx_from_dict(raw: dict[str, Any]) -> TransmitterConfig:
    overrides = raw.get("alerts")
    return TransmitterConfig(
        id=str(raw["id"]),
        name=str(raw.get("name") or raw["id"]),
        model=str(raw.get("model") or "vs300").lower(),
        host=str(raw.get("host") or "").strip(),
        snmp_community=str(raw.get("snmp_community") or "public"),
        snmp_port=int(raw.get("snmp_port") or 161),
        http_port=int(raw.get("http_port") or 80),
        http_username=str(raw.get("http_username") or raw.get("username") or ""),
        http_password=str(raw.get("http_password") or raw.get("password") or ""),
        location=str(raw.get("location") or ""),
        alert_overrides=dict(overrides) if isinstance(overrides, dict) else {},
    )


def _email_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(";", ",").split(",")]
        return tuple(p for p in parts if p)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _alerts_from_dict(raw: dict[str, Any] | None) -> AlertConfig:
    data = raw or {}
    return AlertConfig(
        email_enabled=bool(data.get("email_enabled", False)),
        smtp_host=str(data.get("smtp_host") or ""),
        smtp_port=int(data.get("smtp_port") or 587),
        smtp_username=str(data.get("smtp_username") or ""),
        smtp_password=str(data.get("smtp_password") or ""),
        smtp_tls=bool(data.get("smtp_tls", True)),
        email_from=str(data.get("email_from") or ""),
        email_to=_email_list(data.get("email_to")),
        cooldown_minutes=int(data.get("cooldown_minutes") or 30),
        unreachable_polls=int(data.get("unreachable_polls") or 3),
        on_unreachable=bool(data.get("on_unreachable", True)),
        on_rf_off=bool(data.get("on_rf_off", True)),
        on_tx_alarms=bool(data.get("on_tx_alarms", True)),
        vswr=_optional_float(data.get("vswr")),
        reflected_w=_optional_float(data.get("reflected_w")),
        heatsink_c=_optional_float(data.get("heatsink_c")),
        forward_min_w=_optional_float(data.get("forward_min_w")),
        skip_unconfigured=bool(data.get("skip_unconfigured", True)),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = resolve_config_path(str(path) if path else None)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    raw_text = config_path.read_bytes()
    text: str | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw_text.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_text.decode("utf-8", errors="replace")
    raw = yaml.safe_load(text) or {}

    transmitters = [_tx_from_dict(item) for item in raw.get("transmitters") or []]
    if not transmitters:
        raise ValueError("No transmitters defined in config")

    return AppConfig(
        transmitters=transmitters,
        poll_interval_seconds=int(raw.get("poll_interval_seconds") or 30),
        history_retention_days=int(raw.get("history_retention_days") or 90),
        history_min_interval_seconds=int(
            raw.get("history_min_interval_seconds") or 60
        ),
        http_host=str(raw.get("http_host") or "0.0.0.0"),
        http_port=int(raw.get("http_port") or 8090),
        snmp_timeout_seconds=float(raw.get("snmp_timeout_seconds") or 5.0),
        snmp_retries=int(raw.get("snmp_retries") or 2),
        alerts=_alerts_from_dict(raw.get("alerts")),
    )
