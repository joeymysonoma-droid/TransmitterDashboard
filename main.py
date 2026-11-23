#!/usr/bin/env python3
"""ASMG TX Dashboard — entry point."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

import uvicorn

from nautel_monitor.paths import ensure_app_data_dirs, resolve_config_path


def _setup_logging() -> None:
    handlers: list[logging.Handler] = []
    try:
        log_path = ensure_app_data_dirs() / "logs" / "dashboard.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    except Exception:
        pass
    if sys.stdout is not None:
        try:
            handlers.append(logging.StreamHandler(sys.stdout))
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers or None,
        force=True,
    )


def _port_in_use(host: str, port: int) -> bool:
    check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((check_host, port)) == 0


def _open_browser(port: int) -> None:
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ASMG TX Dashboard — Nautel, AAT, GatesAir, and Crown transmitters.",
    )
    parser.add_argument(
        "-c",
        "--config",
        help=r"Path to transmitters.yaml (default: %%LOCALAPPDATA%%\ASMG TX Dashboard\config\transmitters.yaml when installed)",
    )
    parser.add_argument("--host", help="Override HTTP bind host")
    parser.add_argument("--port", type=int, help="Override HTTP port")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in the default web browser",
    )
    return parser


def main() -> int:
    _setup_logging()
    logger = logging.getLogger("asmg_tx_dashboard")
    args = build_parser().parse_args()

    try:
        config_path = resolve_config_path(args.config)
        from nautel_monitor.config import load_config
        from nautel_monitor.api import create_app

        config = load_config(config_path)
        host = args.host or config.http_host
        port = args.port or config.http_port

        if _port_in_use(host, port):
            logger.info("Dashboard already running on port %s — opening browser", port)
            if args.open_browser:
                webbrowser.open(f"http://localhost:{port}")
            return 0

        app = create_app(config_path)
        logger.info(
            "Starting ASMG TX Dashboard on http://%s:%s (%d transmitters, %d STL) config=%s",
            host if host != "0.0.0.0" else "localhost",
            port,
            len(config.transmitters),
            len(config.stl_devices),
            config_path,
        )
        if args.open_browser:
            threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
        # Windowed PyInstaller builds have sys.stdout/stderr = None; uvicorn's
        # default log config calls isatty() and crashes. Keep our file logging.
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        uvicorn.run(app, host=host, port=port, log_level="info", log_config=None)
        return 0
    except Exception:
        details = traceback.format_exc()
        logger.error("Startup failed:\n%s", details)
        try:
            crash = ensure_app_data_dirs() / "logs" / "crash.log"
            crash.write_text(details, encoding="utf-8")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
