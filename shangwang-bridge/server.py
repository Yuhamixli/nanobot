"""WebSocket server: bridge between nanobot and Avic.exe via CDP."""

import asyncio
import collections
import json
import logging
import re
import shutil
import time
from pathlib import Path

import aiohttp
import websockets

from config import load_config
from cdp import CDPClient

# 与 config.py 一致：默认使用项目 workspace/shangwang-files
_BRIDGE_ROOT = Path(__file__).resolve().parent
_DEFAULT_FILES_DIR = _BRIDGE_ROOT.parent / "workspace" / "shangwang-files"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("shangwang-bridge")

# Single nanobot client
_client: websockets.WebSocketServerProtocol | None = None
_cdp: CDPClient | None = None
_config: dict = {}

# Echo prevention: track recently sent messages to filter self-loop
_sent_texts: collections.deque = collections.deque(maxlen=50)
_my_account_id: str | None = None

# Dedup: track recently forwarded messages (text+session → timestamp)
_recent_forwarded: dict[str, float] = {}
_DEDUP_WINDOW_SEC = 5.0  # ignore same text in same session within 5s


def _safe_filename(name: str) -> str:
    """Remove invalid chars for filesystem."""
    return re.sub(r'[<>:"/\\|?*]', "_", name)[:120]


def _find_in_avicoffice_cache(
    cache_dir: str | Path, file_name: str, dest_dir: Path, base_name: str, ext: str
) -> Path | None:
    """从 AvicOffice 缓存目录查找并复制文件（用户手动下载后可能存于此）。"""
    if not cache_dir or not str(cache_dir).strip():
        return None
    cache = Path(cache_dir).expanduser()
    if not cache.exists():
        return None
    safe_ext = ext.lstrip(".") if ext else "dat"
    target = dest_dir / f"{base_name}.{safe_ext}"
    # 按文件名模糊匹配（可能带时间戳等后缀）
    name_base = Path(file_name).stem if file_name else base_name
    for f in cache.rglob("*"):
        if not f.is_file():
            continue
        if name_base in f.stem or (file_name and f.name == file_name):
            try:
                shutil.copy2(f, target)
                logger.info("已从 AvicOffice 缓存复制: %s -> %s", f.name, target.name)
                return target
            except Exception as e:
                logger.warning("复制缓存文件失败: %s", e)
    return None


async def _download_file(
    url: str, dest_dir: Path, base_name: str, ext: str, cdp: CDPClient | None = None
) -> Path | None:
    """Download file from NIM NOS URL.
    策略顺序: 1) aiohttp 直连; 2) CDP 页面 fetch; 3) CDP 模拟点击下载; 4) AvicOffice 缓存。
    图片通常可直连，文档类( docx/zip 等) NOS 可能返回 403，需点击下载。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_ext = ext.lstrip(".") if ext else "bin"
    if not safe_ext or safe_ext == "bin":
        safe_ext = "dat"
    path = dest_dir / f"{base_name}.{safe_ext}"

    # 1. Try direct aiohttp first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    path.write_bytes(await resp.read())
                    logger.info("已下载文件: %s", path.name)
                    return path
                if resp.status not in (401, 403, 407) or not cdp or not cdp.connected:
                    logger.warning("下载文件失败 HTTP %s: %s", resp.status, url[:80])
                    return None
                logger.info("HTTP %s，尝试通过页面 fetch（带 cookies）下载", resp.status)
    except Exception as e:
        logger.warning("aiohttp 下载失败: %s", e)
        if not cdp or not cdp.connected:
            return None

    # 2. Retry via CDP page fetch (uses browser cookies for NOS auth)
    try:
        data = await cdp.fetch_in_page(url)
        if data:
            path.write_bytes(data)
            logger.info("已通过页面 fetch 下载文件: %s", path.name)
            return path
    except Exception as e:
        logger.warning("页面 fetch 下载失败: %s", e)

    # 3. 模拟点击下载（创建 <a download> 或查找页面中的下载按钮）
    if cdp and cdp.connected:
        try:
            result = await cdp.click_download_and_save(url, dest_dir, base_name, safe_ext)
            if result:
                logger.info("已通过点击下载获取文件: %s", result.name)
                return result
        except Exception as e:
            logger.warning("点击下载失败: %s", e)

    return None


def _try_avicoffice_cache(
    file_name: str, dest_dir: Path, base_name: str, ext: str, cache_dir: str
) -> Path | None:
    """下载失败时的兜底：从 AvicOffice 缓存复制。"""
    return _find_in_avicoffice_cache(cache_dir, file_name, dest_dir, base_name, ext)


async def _connect_cdp() -> bool:
    """Connect to Avic.exe via CDP and inject hooks."""
    global _cdp, _my_account_id
    if _cdp and _cdp.connected:
        return True

    _cdp = CDPClient(
        host=_config.get("cdp_host", "127.0.0.1"),
        port=_config.get("cdp_port", 9222),
    )
    ok = await _cdp.connect()
    if not ok:
        return False

    # Inject NIM message hook
    hooked = await _cdp.inject_hook()
    if not hooked:
        logger.warning("NIM hook 未立即成功，将在轮询时重试")

    # Get my account ID for echo prevention
    try:
        my_id = await _cdp.evaluate(
            "(function(){"
            "var nim=window.__NANOBOT_NIM__;"
            "if(nim&&nim.account)return nim.account;"
            "var el=document.querySelector('#app');"
            "if(el&&el.__vue__&&el.__vue__.$store){"
            "  var s=el.__vue__.$store.state;"
            "  if(s.myInfo&&s.myInfo.account)return s.myInfo.account;"
            "  if(s.userInfo&&s.userInfo.account)return s.userInfo.account;"
            "  if(s.loginInfo&&s.loginInfo.account)return s.loginInfo.account;"
            "  if(s.nim&&s.nim.account)return s.nim.account;"
            "}"
            "return '';"
            "})()"
        )
        if my_id:
            _my_account_id = my_id
            logger.info("当前登录账号: %s", my_id)
        else:
            logger.warning("未获取到登录账号 ID，回显过滤将仅依赖文本匹配")
    except Exception as e:
        logger.warning("获取账号 ID 失败: %s", e)

    return True


async def _ensure_cdp() -> bool:
    """Ensure CDP is connected, reconnect if needed."""
    if _cdp and _cdp.connected:
        return True
    logger.info("尝试重新连接 CDP...")
    return await _connect_cdp()


async def _poll_messages():
    """Poll NIM messages from CDP hook and push to nanobot."""
    interval = _config.get("poll_interval_sec", 3)
    retry_hook_counter = 0

    while True:
        await asyncio.sleep(interval)
        if _client is None:
            continue
        if not await _ensure_cdp():
            continue

        try:
            msgs = await _cdp.poll_messages()

            # If no hook yet, periodically retry injection
            if not _cdp._hooked:
                retry_hook_counter += 1
                if retry_hook_counter % 5 == 1:  # every ~15s
                    logger.info("重试注入 NIM hook...")
                    await _cdp.inject_hook()
                continue

            for msg in msgs:
                text = msg.get("text", "")
                from_id = msg.get("from", "")
                from_nick = msg.get("fromNick") or from_id or "unknown"
                session_id = msg.get("sessionId", "unknown")
                file_url = msg.get("fileUrl", "")
                file_name = msg.get("fileName", "")
                file_ext = msg.get("fileExt", "")

                # --- Echo prevention ---
                # Skip messages with flow='out' (sent by ourselves via NIM SDK)
                if msg.get("flow") == "out":
                    logger.debug("跳过 flow=out: %s", text[:30])
                    continue

                # Skip messages sent by our own account
                if _my_account_id and from_id == _my_account_id:
                    logger.debug("跳过自己发的消息: %s", text[:30])
                    continue

                # Skip if text matches something we recently sent
                if text and text.strip() in _sent_texts:
                    logger.debug("跳过回显消息: %s", text[:30])
                    continue

                # Allow file-only messages (text may be "[图片]" or "[文件]")
                if not text or not text.strip():
                    if not file_url:
                        continue
                    text = "[文件]" if msg.get("msgType") == "file" else "[图片]"

                # Dedup: skip if same text+session was forwarded recently
                dedup_key = f"{session_id}:{text.strip()[:100]}" if not file_url else f"{session_id}:{msg.get('idClient','')}:{file_url[:80]}"
                now = time.time()
                last_time = _recent_forwarded.get(dedup_key, 0)
                if now - last_time < _DEDUP_WINDOW_SEC:
                    logger.debug("跳过重复消息 (%.1fs内): %s", _DEDUP_WINDOW_SEC, text[:30])
                    continue
                _recent_forwarded[dedup_key] = now

                # Cleanup old dedup entries
                if len(_recent_forwarded) > 200:
                    _recent_forwarded.clear()

                # Download file if present
                media_paths = []
                if file_url:
                    files_dir = Path(_config.get("files_dir", str(_DEFAULT_FILES_DIR)))
                    base_name = _safe_filename(f"{session_id}_{msg.get('idClient', '')}"[:80] or "file")
                    ext = file_ext or (file_name.split(".")[-1] if file_name else "")
                    local_path = await _download_file(
                        file_url, files_dir, base_name, ext, cdp=_cdp
                    )
                    if not local_path:
                        # 兜底：从 AvicOffice 缓存复制（用户手动下载后可能存于 C:\Zoolo\AvicOffice Files）
                        cache_dir = _config.get("avicoffice_cache_dir", "")
                        if cache_dir:
                            local_path = _try_avicoffice_cache(
                                file_name or "", files_dir, base_name, ext, cache_dir
                            )
                    if local_path:
                        media_paths.append(str(local_path))
                    else:
                        logger.warning("文件下载失败: url=%s name=%s (NOS 链接可能过期或需鉴权)", file_url[:80], file_name or "(无)")

                is_group = "team" in session_id
                content = text
                # 下载失败时提示 agent，便于回复用户
                if file_url and not media_paths:
                    content = (content + "\n\n[提醒: 附件下载失败，请用户重新发送文件]") if content.strip() else "[提醒: 附件下载失败，请用户重新发送文件]"
                payload = {
                    "type": "message",
                    "sender": from_nick,
                    "sender_id": from_id,
                    "chat_id": session_id,
                    "content": content,
                    "msg_type": msg.get("msgType", "text"),
                    "timestamp": msg.get("time", time.time()),
                    "id_client": msg.get("idClient", ""),
                    "is_group": is_group,
                }
                if media_paths:
                    payload["media"] = media_paths
                try:
                    await _client.send(json.dumps(payload, ensure_ascii=False))
                    logger.info("→ nanobot: [%s] %s: %s%s",
                                session_id[:20],
                                from_nick[:15],
                                text[:50],
                                " (+文件)" if media_paths else "")
                except Exception as e:
                    logger.warning("推送消息失败: %s", e)

        except Exception as e:
            logger.warning("轮询出错: %s", e)
            # CDP connection may be broken
            if _cdp:
                await _cdp.disconnect()


async def _handle_message(ws: websockets.WebSocketServerProtocol, raw: str) -> None:
    """Handle a message from nanobot."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        await ws.send(json.dumps({"type": "error", "error": f"Invalid message: {e}"}))
        return

    msg_type = data.get("type")

    if msg_type == "send":
        text = data.get("text", "")
        chat_id = data.get("chat_id", "")
        if not text:
            await ws.send(json.dumps({"type": "error", "error": "text is empty"}))
            return
        if not await _ensure_cdp():
            await ws.send(json.dumps({"type": "error", "error": "CDP 未连接，请确认 Avic.exe 启动参数"}))
            return

        # Record sent text for echo prevention
        _sent_texts.append(text.strip())

        result = await _cdp.send_text(chat_id, text)
        # 若 CDP 超时，重试一次
        if not result.get("ok") and "timed out" in str(result.get("error", "")).lower():
            logger.warning("CDP send_text 超时，重试一次")
            await asyncio.sleep(2)
            result = await _cdp.send_text(chat_id, text)
        if result.get("ok"):
            await ws.send(json.dumps({"type": "status", "status": "sent"}))
            logger.info("← nanobot: 已发送到 [%s]: %s", chat_id[:20], text[:50])
        else:
            await ws.send(json.dumps({"type": "error", "error": result.get("error", "send failed")}))

    elif msg_type == "sessions":
        # Query session list
        if not await _ensure_cdp():
            await ws.send(json.dumps({"type": "error", "error": "CDP 未连接"}))
            return
        info = await _cdp.get_session_info()
        await ws.send(json.dumps({"type": "sessions", "data": info}, ensure_ascii=False))

    elif msg_type == "ping":
        await ws.send(json.dumps({"type": "status", "status": "pong"}))

    elif msg_type == "my_id":
        await ws.send(json.dumps({
            "type": "my_id",
            "account": _my_account_id or "",
        }))

    elif msg_type == "fetch_current_chat":
        if not await _ensure_cdp():
            await ws.send(json.dumps({"type": "error", "error": "CDP 未连接"}))
        else:
            result = await _cdp.fetch_current_chat()
            await ws.send(json.dumps({"type": "fetch_current_chat", **result}, ensure_ascii=False))

    elif msg_type == "current_session":
        if not await _ensure_cdp():
            await ws.send(json.dumps({"type": "error", "error": "CDP 未连接"}))
        else:
            info = await _cdp.get_session_info()
            curr = info.get("currSession", "")
            other_party_id = ""
            if curr.startswith("p2p-"):
                other_party_id = curr[4:]
            elif curr.startswith("team-"):
                other_party_id = curr[5:]
            await ws.send(json.dumps({
                "type": "current_session",
                "currSession": curr,
                "otherPartyId": other_party_id,
                "myAccount": _my_account_id or "",
                "sessions": info.get("sessions", []),
            }, ensure_ascii=False))

    elif msg_type == "rehook":
        # Force re-inject hook
        if _cdp and _cdp.connected:
            _cdp._hooked = False
            ok = await _cdp.inject_hook()
            await ws.send(json.dumps({"type": "status", "status": "hooked" if ok else "hook_failed"}))
        else:
            await ws.send(json.dumps({"type": "error", "error": "CDP 未连接"}))


async def _handler(ws: websockets.WebSocketServerProtocol) -> None:
    """Handle avic shangwang bridge client WebSocket connection."""
    global _client
    is_primary = _client is None
    if is_primary:
        _client = ws
    logger.info("✓ AVIC shangwang bridge client connected" + (" (primary)" if is_primary else " (query)"))

    # Try CDP connection
    cdp_ok = await _connect_cdp()
    status = "ready" if cdp_ok else "cdp_not_connected"
    await ws.send(json.dumps({"type": "status", "status": status}))

    if not cdp_ok:
        logger.warning("CDP 未连接 — 请确认 Avic.exe 以 --remote-debugging-port=%s 启动",
                        _config.get("cdp_port", 9222))

    try:
        async for message in ws:
            await _handle_message(ws, message)
    except websockets.ConnectionClosed:
        pass
    finally:
        if _client is ws:
            _client = None
            logger.info("✗ primary client disconnected (gateway 已断开，将停止推送消息)")
        else:
            logger.info("✗ query client disconnected (查询命令结束，gateway 保持连接)")


async def serve() -> None:
    """Start the bridge server."""
    global _config
    _config = load_config()
    host = _config["ws_host"]
    port = _config["ws_port"]
    cdp_port = _config["cdp_port"]

    logger.info("=" * 50)
    logger.info("商网办公 Bridge (CDP 模式)")
    logger.info("=" * 50)
    logger.info("Bridge WebSocket: ws://%s:%s", host, port)
    logger.info("CDP 目标: http://%s:%s", _config["cdp_host"], cdp_port)
    logger.info("")
    logger.info("请确保:")
    logger.info("  1. Avic.exe 已以调试模式启动:")
    logger.info('     "C:\\Program Files (x86)\\AVIC Office\\Avic.exe" --remote-debugging-port=%s', cdp_port)
    logger.info("  2. 已手动登录商网办公")
    logger.info("  3. nanobot gateway 已配置 bridgeUrl = ws://localhost:%s", port)
    logger.info("=" * 50)

    # Start message polling task
    loop = asyncio.get_event_loop()
    loop.create_task(_poll_messages())

    async with websockets.serve(_handler, host, port, ping_interval=20, ping_timeout=10):
        await asyncio.Future()  # run forever
