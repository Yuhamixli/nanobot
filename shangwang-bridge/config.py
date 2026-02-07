"""Load config from env and optional config.json."""

import json
import os
from pathlib import Path


def load_config() -> dict:
    root = Path(__file__).resolve().parent
    cfg: dict = {
        # WebSocket server (bridge ↔ nanobot)
        "ws_host": os.environ.get("SHANGWANG_WS_HOST", "0.0.0.0"),
        "ws_port": int(os.environ.get("SHANGWANG_WS_PORT", "3010")),
        # CDP (Electron remote debugging)
        "cdp_host": os.environ.get("SHANGWANG_CDP_HOST", "127.0.0.1"),
        "cdp_port": int(os.environ.get("SHANGWANG_CDP_PORT", "9222")),
        # Polling
        "poll_interval_sec": float(os.environ.get("SHANGWANG_POLL_INTERVAL", "3")),
    }
    config_file = root / "config.json"
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
            cfg.update({k: v for k, v in data.items() if k in cfg})
        except Exception:
            pass
    return cfg
