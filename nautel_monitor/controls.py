"""Gated RF control dispatch for ASMG TX Dashboard."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from .aat_client import set_aat_rf
from .crown_client import set_crown_rf
from .flexiva_client import set_flexiva_rf
from .models import (
    AppConfig,
    TransmitterConfig,
    TransmitterReading,
    is_aat_model,
    is_crown_model,
    is_flexiva_model,
)
from .oids import profile_for
from .snmp_client import SnmpError, snmp_set

logger = logging.getLogger(__name__)

ACTIONS = frozenset({"rf_on", "rf_off"})


class ControlError(RuntimeError):
    """User-facing control failure (auth, gating, vendor refusal)."""


class ControlNotReady(ControlError):
    """Control path exists but needs live validation / missing protocol details."""


def model_family(model: str) -> str:
    m = model.lower().strip()
    if is_flexiva_model(m):
        return "flexiva"
    if is_aat_model(m):
        return "aat"
    if is_crown_model(m):
        return "crown"
    if m.startswith("vx"):
        return "vx"
    if m.startswith("vs"):
        return "vs300"
    return m


SUPPORTED_ACTIONS: dict[str, list[str]] = {
    "vs300": ["rf_on", "rf_off"],
    "vx": ["rf_on", "rf_off"],
    "aat": ["rf_on", "rf_off"],
    "flexiva": ["rf_on", "rf_off"],
    "crown": ["rf_on", "rf_off"],
}


def controls_status(config: AppConfig) -> dict[str, Any]:
    enabled = bool(config.controls.enabled)
    password_set = bool(config.controls.password.strip())
    return {
        "enabled": enabled,
        "password_required": True,
        "password_configured": password_set,
        "supported_actions_by_model": dict(SUPPORTED_ACTIONS),
        "experimental": ["flexiva", "crown"],
        "note": (
            "RF controls default off. Enable in Settings, set a controls password, "
            "and confirm each command. Flexiva/Crown are experimental — do not "
            "test live until ready."
        ),
    }


def tx_controls_enabled(config: AppConfig, tx: TransmitterConfig) -> bool:
    if tx.controls_enabled is False:
        return False
    if tx.controls_enabled is True:
        return True
    return bool(config.controls.enabled)


def expected_password(config: AppConfig, tx: TransmitterConfig) -> str:
    if tx.controls_password.strip():
        return tx.controls_password
    return config.controls.password


def verify_password(config: AppConfig, tx: TransmitterConfig, password: str) -> None:
    expected = expected_password(config, tx)
    if not expected.strip():
        raise ControlError(
            "Controls password is not configured. Set controls.password in Settings."
        )
    if not hmac.compare_digest(str(password or ""), expected):
        raise ControlError("Incorrect controls password")


def supported_actions_for(tx: TransmitterConfig) -> list[str]:
    family = model_family(tx.model)
    if family.startswith("vs"):
        family = "vs300"
    if family.startswith("vx"):
        family = "vx"
    return list(SUPPORTED_ACTIONS.get(family, []))


def send_control(
    config: AppConfig,
    tx: TransmitterConfig,
    action: str,
    *,
    password: str,
    reading: TransmitterReading | None = None,
) -> str:
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ControlError(f"Unknown action: {action}")
    if not tx.configured:
        raise ControlError("Transmitter host is not configured")
    if not tx_controls_enabled(config, tx):
        raise ControlError("RF controls are disabled for this transmitter")
    verify_password(config, tx, password)

    supported = supported_actions_for(tx)
    if action not in supported:
        raise ControlError(f"Action {action} is not supported for model {tx.model}")

    logger.info("RF control requested: tx=%s action=%s", tx.id, action)
    try:
        message = _dispatch(config, tx, action, reading=reading)
    except ControlError:
        logger.warning("RF control failed: tx=%s action=%s", tx.id, action)
        raise
    except Exception as error:
        logger.exception("RF control error: tx=%s action=%s", tx.id, action)
        raise ControlError(str(error)) from error
    logger.info("RF control ok: tx=%s action=%s msg=%s", tx.id, action, message[:120])
    return message


def _dispatch(
    config: AppConfig,
    tx: TransmitterConfig,
    action: str,
    *,
    reading: TransmitterReading | None,
) -> str:
    on = action == "rf_on"
    if tx.is_aat:
        return set_aat_rf(tx, on=on, timeout=config.snmp_timeout_seconds)
    if tx.is_flexiva:
        return set_flexiva_rf(tx, on=on, timeout=config.snmp_timeout_seconds)
    if tx.is_crown:
        return set_crown_rf(tx, on=on, timeout=max(8.0, config.snmp_timeout_seconds))
    return _set_nautel_rf(config, tx, on=on, reading=reading)


def _rf_oid_for(model: str) -> str:
    meters, _alarms = profile_for(model)
    for meter in meters:
        if meter.key == "rf_state":
            return meter.oid
    raise ControlError(f"No RF on/off OID for model {model}")


def _set_nautel_rf(
    config: AppConfig,
    tx: TransmitterConfig,
    *,
    on: bool,
    reading: TransmitterReading | None,
) -> str:
    if reading is not None and reading.local_remote is not None and reading.local_remote != 1:
        raise ControlError(
            f"{tx.name} is in LOCAL mode (local_remote={reading.local_remote}). "
            "Switch the transmitter to REMOTE before SNMP RF control."
        )
    oid = _rf_oid_for(tx.model)
    value = 1 if on else 0
    try:
        snmp_set(
            host=tx.host,
            community=tx.write_community,
            bindings=[(oid, value)],
            port=tx.snmp_port,
            timeout=config.snmp_timeout_seconds,
            retries=config.snmp_retries,
        )
    except SnmpError as error:
        raise ControlError(f"SNMP SET failed: {error}") from error
    state = "ON" if on else "OFF"
    return f"SNMP RF {state} sent to {tx.name} ({oid}={value})"
