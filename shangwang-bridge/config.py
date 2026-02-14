"""Load config from env, bridge config.json, and nanobot 主配置（优先）。"""

import json
import os
from pathlib import Path


def _read_nanobot_config() -> dict:
    """读取 nanobot 主配置（~/.nanobot/config.json），bridge 与 nanobot 共用时优先使用。"""
    path = Path(os.environ.get("NANOBOT_CONFIG", str(Path.home() / ".nanobot" / "config.json")))
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config() -> dict:
    root = Path(__file__).resolve().parent
    # 项目 workspace：与 nanobot 统一，商网附件集中在此
    project_workspace = root.parent / "workspace"
    default_files_dir = project_workspace / "shangwang-files"
    cfg: dict = {
        # WebSocket server (bridge ↔ nanobot)
        "ws_host": os.environ.get("SHANGWANG_WS_HOST", "0.0.0.0"),
        "ws_port": int(os.environ.get("SHANGWANG_WS_PORT", "3010")),
        # CDP (Electron remote debugging)
        "cdp_host": os.environ.get("SHANGWANG_CDP_HOST", "127.0.0.1"),
        "cdp_port": int(os.environ.get("SHANGWANG_CDP_PORT", "9222")),
        # Polling
        "poll_interval_sec": float(os.environ.get("SHANGWANG_POLL_INTERVAL", "3")),
        # File download (NIM NOS)，默认写入 workspace/shangwang-files，channel 会复制到 knowledge
        "files_dir": os.environ.get("SHANGWANG_FILES_DIR", str(default_files_dir)),
        "avicoffice_cache_dir": "",
    }
    # Bridge 自身 config.json
    config_file = root / "config.json"
    bridge_data: dict = {}
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                bridge_data = json.load(f)
            cfg.update({k: v for k, v in bridge_data.items() if k in cfg})
        except Exception:
            pass
    # avicoffice_cache_dir：优先从 nanobot 主配置读取（channels.shangwang.avicofficeCacheDir）
    # 优先级：环境变量 > bridge config.json > nanobot config > 空
    avicoffice = (
        os.environ.get("SHANGWANG_AVICOFFICE_CACHE")
        or bridge_data.get("avicoffice_cache_dir")
        or ""
    )
    if not avicoffice:
        nb = _read_nanobot_config()
        sw = nb.get("channels", {}).get("shangwang", {})
        avicoffice = sw.get("avicofficeCacheDir") or sw.get("avicoffice_cache_dir") or ""
    cfg["avicoffice_cache_dir"] = (avicoffice or "").strip()
    return cfg
