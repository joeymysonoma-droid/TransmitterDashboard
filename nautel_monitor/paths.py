"""Resolve filesystem paths for development, PyInstaller, and installed builds."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "ASMG TX Dashboard"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def app_data_dir() -> Path:
    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    return project_root()


def ensure_app_data_dirs() -> Path:
    base = app_data_dir()
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "config").mkdir(parents=True, exist_ok=True)
    return base


def static_dir() -> Path:
    candidates = [
        bundle_dir() / "static",
        project_root() / "static",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return project_root() / "static"


def data_dir() -> Path:
    if is_frozen():
        base = ensure_app_data_dirs()
        return base / "data"
    path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_config_example() -> Path:
    candidates = [
        bundle_dir() / "transmitters.example.yaml",
        bundle_dir() / "config" / "transmitters.example.yaml",
        project_root() / "config" / "transmitters.example.yaml",
        project_root() / "config" / "transmitters.yaml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("transmitters.example.yaml not found in application bundle")


def resolve_config_path(config_arg: str | None = None) -> Path:
    if config_arg:
        return Path(config_arg).expanduser()

    if is_frozen():
        base = ensure_app_data_dirs()
        config_path = base / "config" / "transmitters.yaml"
        if not config_path.exists():
            shutil.copy2(bundled_config_example(), config_path)
        return config_path

    return project_root() / "config" / "transmitters.yaml"
