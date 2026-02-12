"""WebSocket server: bridge between nanobot and Avic.exe via CDP."""

import asyncio
import collections
import json
import logging
import time

import websockets

from config import load_config
from cdp import CDPClient

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

                # Skip empty messages
                if not text or not text.strip():
                    continue

                # Dedup: skip if same text+session was forwarded recently
                dedup_key = f"{session_id}:{text.strip()[:100]}"
                now = time.time()
                last_time = _recent_forwarded.get(dedup_key, 0)
                if now - last_time < _DEDUP_WINDOW_SEC:
                    logger.debug("跳过重复消息 (%.1fs内): %s", _DEDUP_WINDOW_SEC, text[:30])
                    continue
                _recent_forwarded[dedup_key] = now

                # Cleanup old dedup entries
                if len(_recent_forwarded) > 200:
                    cutoff = now - _DEDUP_WINDOW_SEC * 2
                    _recent_forwarded.clear()

                is_group = "team" in session_id
                payload = {
                    "type": "message",
                    "sender": from_nick,
                    "chat_id": session_id,
                    "content": text,
                    "msg_type": msg.get("msgType", "text"),
                    "timestamp": msg.get("time", time.time()),
                    "is_group": is_group,
                }
                try:
                    await _client.send(json.dumps(payload, ensure_ascii=False))
                    logger.info("→ nanobot: [%s] %s: %s",
                                session_id[:20],
                                from_nick[:15],
                                text[:50])
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
    _client = ws
    logger.info("✓ AVIC shangwang bridge client connected")

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
        _client = None
        logger.info("✗ avic shangwang bridge client disconnected")


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
