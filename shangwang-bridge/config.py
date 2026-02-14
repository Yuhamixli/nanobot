"""Load config from env and optional config.json."""

import json
import os
from pathlib import Path


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
        # AvicOffice 应用缓存目录，下载失败时可尝试从此处复制（如 C:\Zoolo\AvicOffice Files）
        "avicoffice_cache_dir": os.environ.get("SHANGWANG_AVICOFFICE_CACHE", ""),
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
