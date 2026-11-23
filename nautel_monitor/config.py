"""Load and save transmitter dashboard configuration from YAML."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AAT_MODELS,
    CROWN_MODELS,
    FLEXIVA_MODELS,
    BRICLINK_MODELS,
    COMREX_MODELS,
    HDLINK_MODELS,
    IPLINK_MODELS,
    INSTREAM_MODELS,
    AlertConfig,
    AppConfig,
    ControlsConfig,
    StlDeviceConfig,
    TransmitterConfig,
)
from .paths import resolve_config_path

DEFAULT_CONFIG = resolve_config_path()
PASSWORD_MASK = "********"

ALLOWED_MODELS = frozenset(
    {
        "vs300",
        "vs",
        "vx",
        "vx2",
        "vx2.5",
        *FLEXIVA_MODELS,
        *AAT_MODELS,
        *CROWN_MODELS,
    }
)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return bool(value)


STL_MODELS = frozenset(
    {
        *HDLINK_MODELS,
        *IPLINK_MODELS,
        *COMREX_MODELS,
        *BRICLINK_MODELS,
        *INSTREAM_MODELS,
    }
)


def _stl_from_dict(raw: dict[str, Any]) -> StlDeviceConfig:
    overrides = raw.get("alerts")
    model = str(raw.get("model") or "hdlink").lower().strip()
    return StlDeviceConfig(
        id=str(raw["id"]).strip(),
        name=str(raw.get("name") or raw["id"]),
        model=model,
        host=str(raw.get("host") or "").strip(),
        snmp_community=str(raw.get("snmp_community") or "public"),
        snmp_port=int(raw.get("snmp_port") or 161),
        location=str(raw.get("location") or ""),
        alert_overrides=dict(overrides) if isinstance(overrides, dict) else {},
        related_tx_id=str(raw.get("related_tx_id") or "").strip(),
        http_password=str(raw.get("http_password") or ""),
    )


def _tx_from_dict(raw: dict[str, Any]) -> TransmitterConfig:
    overrides = raw.get("alerts")
    controls_enabled = raw.get("controls_enabled")
    if "controls_enabled" not in raw and isinstance(raw.get("controls"), dict):
        controls_enabled = raw["controls"].get("enabled")
    controls_password = str(raw.get("controls_password") or "")
    if not controls_password and isinstance(raw.get("controls"), dict):
        controls_password = str(raw["controls"].get("password") or "")
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
        controls_enabled=_optional_bool(controls_enabled),
        controls_password=controls_password,
        snmp_write_community=str(raw.get("snmp_write_community") or ""),
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


def _controls_from_dict(raw: dict[str, Any] | None) -> ControlsConfig:
    data = raw or {}
    return ControlsConfig(
        enabled=bool(data.get("enabled", False)),
        password=str(data.get("password") or ""),
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
    stl_devices = [_stl_from_dict(item) for item in raw.get("stl_devices") or []]

    return AppConfig(
        transmitters=transmitters,
        stl_devices=stl_devices,
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
        controls=_controls_from_dict(raw.get("controls")),
    )


def _alerts_to_dict(alerts: AlertConfig) -> dict[str, Any]:
    return {
        "email_enabled": alerts.email_enabled,
        "smtp_host": alerts.smtp_host,
        "smtp_port": alerts.smtp_port,
        "smtp_username": alerts.smtp_username,
        "smtp_password": alerts.smtp_password,
        "smtp_tls": alerts.smtp_tls,
        "email_from": alerts.email_from,
        "email_to": list(alerts.email_to),
        "cooldown_minutes": alerts.cooldown_minutes,
        "unreachable_polls": alerts.unreachable_polls,
        "on_unreachable": alerts.on_unreachable,
        "on_rf_off": alerts.on_rf_off,
        "on_tx_alarms": alerts.on_tx_alarms,
        "vswr": alerts.vswr,
        "reflected_w": alerts.reflected_w,
        "heatsink_c": alerts.heatsink_c,
        "forward_min_w": alerts.forward_min_w,
        "skip_unconfigured": alerts.skip_unconfigured,
    }


def _controls_to_dict(controls: ControlsConfig) -> dict[str, Any]:
    return {
        "enabled": controls.enabled,
        "password": controls.password,
    }


def _stl_to_dict(device: StlDeviceConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "name": device.name,
        "model": device.model,
        "host": device.host,
        "snmp_community": device.snmp_community,
        "snmp_port": device.snmp_port,
        "location": device.location,
    }
    if device.http_password:
        payload["http_password"] = device.http_password
    if device.related_tx_id:
        payload["related_tx_id"] = device.related_tx_id
    if device.alert_overrides:
        payload["alerts"] = dict(device.alert_overrides)
    return payload


def _tx_to_dict(tx: TransmitterConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": tx.id,
        "name": tx.name,
        "model": tx.model,
        "host": tx.host,
        "snmp_community": tx.snmp_community,
        "snmp_port": tx.snmp_port,
        "http_port": tx.http_port,
        "http_username": tx.http_username,
        "http_password": tx.http_password,
        "location": tx.location,
    }
    if tx.snmp_write_community:
        payload["snmp_write_community"] = tx.snmp_write_community
    if tx.controls_enabled is not None:
        payload["controls_enabled"] = tx.controls_enabled
    if tx.controls_password:
        payload["controls_password"] = tx.controls_password
    if tx.alert_overrides:
        payload["alerts"] = dict(tx.alert_overrides)
    return payload


def config_to_dict(config: AppConfig, *, mask_secrets: bool = False) -> dict[str, Any]:
    alerts = _alerts_to_dict(config.alerts)
    controls = _controls_to_dict(config.controls)
    transmitters = [_tx_to_dict(tx) for tx in config.transmitters]
    stl_devices = [_stl_to_dict(device) for device in config.stl_devices]
    if mask_secrets:
        if alerts.get("smtp_password"):
            alerts["smtp_password"] = PASSWORD_MASK
        if controls.get("password"):
            controls["password"] = PASSWORD_MASK
        for tx in transmitters:
            if tx.get("http_password"):
                tx["http_password"] = PASSWORD_MASK
            if tx.get("controls_password"):
                tx["controls_password"] = PASSWORD_MASK
        for device in stl_devices:
            if device.get("snmp_community"):
                device["snmp_community"] = PASSWORD_MASK
            if device.get("http_password"):
                device["http_password"] = PASSWORD_MASK
    return {
        "poll_interval_seconds": config.poll_interval_seconds,
        "history_retention_days": config.history_retention_days,
        "history_min_interval_seconds": config.history_min_interval_seconds,
        "http_host": config.http_host,
        "http_port": config.http_port,
        "snmp_timeout_seconds": config.snmp_timeout_seconds,
        "snmp_retries": config.snmp_retries,
        "alerts": alerts,
        "controls": controls,
        "transmitters": transmitters,
        "stl_devices": stl_devices,
    }


def validate_config_dict(raw: dict[str, Any]) -> AppConfig:
    if not isinstance(raw, dict):
        raise ValueError("Config must be an object")
    transmitters_raw = raw.get("transmitters") or []
    if not isinstance(transmitters_raw, list) or not transmitters_raw:
        raise ValueError("At least one transmitter is required")

    transmitters: list[TransmitterConfig] = []
    seen_ids: set[str] = set()
    for item in transmitters_raw:
        if not isinstance(item, dict):
            raise ValueError("Each transmitter must be an object")
        if not item.get("id"):
            raise ValueError("Each transmitter needs an id")
        tx = _tx_from_dict(item)
        if tx.id in seen_ids:
            raise ValueError(f"Duplicate transmitter id: {tx.id}")
        seen_ids.add(tx.id)
        model = tx.model.lower().strip()
        if model not in ALLOWED_MODELS and not (
            model.startswith("vs") or model.startswith("vx")
        ):
            raise ValueError(f"Unsupported model: {tx.model}")
        if tx.snmp_port < 1 or tx.snmp_port > 65535:
            raise ValueError(f"Invalid snmp_port for {tx.id}")
        if tx.http_port < 1 or tx.http_port > 65535:
            raise ValueError(f"Invalid http_port for {tx.id}")
        transmitters.append(tx)

    stl_raw = raw.get("stl_devices") or []
    if not isinstance(stl_raw, list):
        raise ValueError("stl_devices must be a list")
    stl_devices: list[StlDeviceConfig] = []
    seen_stl: set[str] = set()
    for item in stl_raw:
        if not isinstance(item, dict):
            raise ValueError("Each STL device must be an object")
        if not item.get("id"):
            raise ValueError("Each STL device needs an id")
        device = _stl_from_dict(item)
        if device.id in seen_stl:
            raise ValueError(f"Duplicate STL id: {device.id}")
        seen_stl.add(device.id)
        if device.model not in STL_MODELS:
            raise ValueError(f"Unsupported STL model: {device.model}")
        if device.snmp_port < 1 or device.snmp_port > 65535:
            raise ValueError(f"Invalid snmp_port for {device.id}")
        stl_devices.append(device)

    http_port = int(raw.get("http_port") or 8090)
    if http_port < 1 or http_port > 65535:
        raise ValueError("Invalid http_port")

    return AppConfig(
        transmitters=transmitters,
        stl_devices=stl_devices,
        poll_interval_seconds=max(5, int(raw.get("poll_interval_seconds") or 30)),
        history_retention_days=max(1, int(raw.get("history_retention_days") or 90)),
        history_min_interval_seconds=max(
            5, int(raw.get("history_min_interval_seconds") or 60)
        ),
        http_host=str(raw.get("http_host") or "0.0.0.0"),
        http_port=http_port,
        snmp_timeout_seconds=float(raw.get("snmp_timeout_seconds") or 5.0),
        snmp_retries=max(0, int(raw.get("snmp_retries") or 2)),
        alerts=_alerts_from_dict(raw.get("alerts")),
        controls=_controls_from_dict(raw.get("controls")),
    )


def merge_secrets(incoming: AppConfig, existing: AppConfig) -> AppConfig:
    """Keep existing secrets when masked or omitted."""
    existing_by_id = {tx.id: tx for tx in existing.transmitters}
    merged_txs: list[TransmitterConfig] = []
    for tx in incoming.transmitters:
        prev = existing_by_id.get(tx.id)
        password = tx.http_password
        if password == PASSWORD_MASK:
            password = prev.http_password if prev else ""
        elif password is None:
            password = prev.http_password if prev else ""
        ctrl_password = tx.controls_password
        if ctrl_password == PASSWORD_MASK:
            ctrl_password = prev.controls_password if prev else ""
        merged_txs.append(
            TransmitterConfig(
                id=tx.id,
                name=tx.name,
                model=tx.model,
                host=tx.host,
                snmp_community=tx.snmp_community,
                snmp_port=tx.snmp_port,
                http_port=tx.http_port,
                http_username=tx.http_username,
                http_password=password,
                location=tx.location,
                alert_overrides=dict(tx.alert_overrides),
                controls_enabled=tx.controls_enabled,
                controls_password=ctrl_password,
                snmp_write_community=tx.snmp_write_community,
            )
        )

    existing_stl = {device.id: device for device in existing.stl_devices}
    merged_stl: list[StlDeviceConfig] = []
    for device in incoming.stl_devices:
        prev = existing_stl.get(device.id)
        community = device.snmp_community
        if community == PASSWORD_MASK:
            community = prev.snmp_community if prev else "public"
        http_password = device.http_password
        if http_password == PASSWORD_MASK:
            http_password = prev.http_password if prev else ""
        merged_stl.append(
            StlDeviceConfig(
                id=device.id,
                name=device.name,
                model=device.model,
                host=device.host,
                snmp_community=community,
                snmp_port=device.snmp_port,
                location=device.location,
                alert_overrides=dict(device.alert_overrides),
                related_tx_id=device.related_tx_id,
                http_password=http_password,
            )
        )

    smtp_password = incoming.alerts.smtp_password
    if smtp_password == PASSWORD_MASK:
        smtp_password = existing.alerts.smtp_password

    controls_password = incoming.controls.password
    if controls_password == PASSWORD_MASK:
        controls_password = existing.controls.password

    alerts = AlertConfig(
        email_enabled=incoming.alerts.email_enabled,
        smtp_host=incoming.alerts.smtp_host,
        smtp_port=incoming.alerts.smtp_port,
        smtp_username=incoming.alerts.smtp_username,
        smtp_password=smtp_password,
        smtp_tls=incoming.alerts.smtp_tls,
        email_from=incoming.alerts.email_from,
        email_to=incoming.alerts.email_to,
        cooldown_minutes=incoming.alerts.cooldown_minutes,
        unreachable_polls=incoming.alerts.unreachable_polls,
        on_unreachable=incoming.alerts.on_unreachable,
        on_rf_off=incoming.alerts.on_rf_off,
        on_tx_alarms=incoming.alerts.on_tx_alarms,
        vswr=incoming.alerts.vswr,
        reflected_w=incoming.alerts.reflected_w,
        heatsink_c=incoming.alerts.heatsink_c,
        forward_min_w=incoming.alerts.forward_min_w,
        skip_unconfigured=incoming.alerts.skip_unconfigured,
    )
    return AppConfig(
        transmitters=merged_txs,
        stl_devices=merged_stl,
        poll_interval_seconds=incoming.poll_interval_seconds,
        history_retention_days=incoming.history_retention_days,
        history_min_interval_seconds=incoming.history_min_interval_seconds,
        http_host=incoming.http_host,
        http_port=incoming.http_port,
        snmp_timeout_seconds=incoming.snmp_timeout_seconds,
        snmp_retries=incoming.snmp_retries,
        alerts=alerts,
        controls=ControlsConfig(
            enabled=incoming.controls.enabled,
            password=controls_password,
        ),
    )


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = config_to_dict(config, mask_secrets=False)
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    fd, tmp_name = tempfile.mkstemp(
        prefix=config_path.name + ".",
        suffix=".tmp",
        dir=str(config_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, config_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
