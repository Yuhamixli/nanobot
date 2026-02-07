"""商网办公 channel: connects to shangwang-bridge via WebSocket."""

import asyncio
import json

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import ShangwangConfig


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

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through 商网 bridge."""
        if not self._ws or not self._connected:
            logger.warning("商网 bridge not connected")
            return
        try:
            payload = {"type": "send", "chat_id": msg.chat_id, "text": msg.content}
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
            if not self.is_allowed(sender):
                return
            await self._handle_message(
                sender_id=sender,
                chat_id=chat_id,
                content=content,
                metadata={"timestamp": data.get("timestamp")},
            )
        elif msg_type == "status":
            logger.info("商网 bridge status: {}", data.get("status"))
            if data.get("status") == "ready":
                self._connected = True
            elif data.get("status") in ("disconnected", "sent"):
                pass
        elif msg_type == "error":
            logger.error("商网 bridge error: {}", data.get("error"))
