"""商网办公 channel: connects to shangwang-bridge via WebSocket."""

import asyncio
import json
import re

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import ShangwangConfig


def _markdown_to_plain_text(text: str) -> str:
    """将 Markdown 转为纯文本，商网办公无法渲染 Markdown 时使用。"""
    if not text:
        return text
    t = text
    # 代码块 ```...``` -> 保留内容
    t = re.sub(r"```(?:[\w]*\n)?(.*?)```", r"\1", t, flags=re.DOTALL)
    # 行内代码 `...` -> 保留内容
    t = re.sub(r"`([^`]+)`", r"\1", t)
    # 链接 [text](url) -> text
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    # 加粗 **text** 或 __text__
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    # 斜体 *text* 或 _text_（避免误伤列表）
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", t)
    t = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"\1", t)
    # 标题 ## -> 去掉井号，保留内容
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    # 多余空行压缩
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


class ShangwangChannel(BaseChannel):
    """
    ‌商网 channel that connects to shangwang-bridge (Windows, China-only).
    No Windows or UI code here; protocol only.
    """

    name = "shangwang"

    def __init__(self, config: ShangwangConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: ShangwangConfig = config
        self._ws = None
        self._connected = False

    async def start(self) -> None:
        """Connect to shangwang-bridge and listen."""
        import websockets

        bridge_url = self.config.bridge_url
        logger.info("Connecting to 商网 bridge at {}...", bridge_url)

        self._running = True

        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("Connected to 商网 bridge")

                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error("Error handling 商网 bridge message: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning("商网 bridge connection error: {}", e)
                if self._running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the channel."""
        self._running = False
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    def _is_mentioned(self, content: str) -> bool:
        """检查消息是否 @提及 了任一配置的昵称。"""
        if not content or not self.config.mention_names:
            return False
        for name in self.config.mention_names:
            if not name:
                continue
            if f"@{name}" in content:
                return True
        return False

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through 商网 bridge. 商网无法渲染 Markdown，自动转为纯文本。"""
        if not self._ws or not self._connected:
            logger.warning("商网 bridge not connected")
            return
        try:
            plain = _markdown_to_plain_text(msg.content)
            # 群聊回复截断至配置的最大字数
            if "team" in msg.chat_id:
                max_len = self.config.group_reply_max_length
                if len(plain) > max_len:
                    plain = plain[:max_len].rstrip() + "…"
                    logger.debug("群聊回复已截断至 %d 字", max_len)
            payload = {"type": "send", "chat_id": msg.chat_id, "text": plain}
            await self._ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error("Error sending 商网 message: %s", e)

    async def _handle_bridge_message(self, raw: str | bytes) -> None:
        """Handle a message from the bridge."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from 商网 bridge: %s", raw[:100])
            return

        msg_type = data.get("type")

        if msg_type == "message":
            sender = data.get("sender", "shangwang")
            chat_id = data.get("chat_id", "current")
            content = data.get("content", "")
            is_group = data.get("is_group", False)

            if not self.is_allowed(sender):
                return

            # 群聊：仅当配置了 mention_names 且消息 @提及 了任一配置名时才回复
            if is_group and self.config.mention_names:
                if not self._is_mentioned(content):
                    logger.debug("群聊消息未 @提及 配置昵称，跳过: %s", content[:50])
                    return

            # 私聊：过短消息（如「好的」「1」、emoji）不回复
            if not is_group and self.config.skip_short_replies:
                stripped = content.strip()
                if len(stripped) <= self.config.short_reply_max_length:
                    logger.debug("私聊消息过短，跳过: %s", repr(stripped[:20]))
                    return

            await self._handle_message(
                sender_id=sender,
                chat_id=chat_id,
                content=content,
                metadata={"timestamp": data.get("timestamp"), "is_group": is_group},
            )
        elif msg_type == "status":
            logger.info("商网 bridge status: {}", data.get("status"))
            if data.get("status") == "ready":
                self._connected = True
            elif data.get("status") in ("disconnected", "sent"):
                pass
        elif msg_type == "error":
            logger.error("商网 bridge error: {}", data.get("error"))
