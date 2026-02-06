"""企业微信 (WeCom) channel implementation."""

import asyncio
import time
from typing import Any

import httpx
from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WeComConfig

TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"


class WeComChannel(BaseChannel):
    """
    企业微信通道：通过企业微信应用向成员发送消息。

    配置 corp_id、agent_id、secret 后即可发送。接收用户消息需在企业微信后台
    配置「接收消息」回调 URL（后续版本可支持）。
    """

    name = "wecom"

    def __init__(self, config: WeComConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WeComConfig = config
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _get_token(self) -> str | None:
        """获取或刷新 access_token（带简单缓存）。"""
        now = time.monotonic()
        if self._access_token and self._token_expires_at > now:
            return self._access_token
        async with self._lock:
            if self._access_token and self._token_expires_at > now:
                return self._access_token
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        TOKEN_URL,
                        params={
                            "corpid": self.config.corp_id,
                            "corpsecret": self.config.secret,
                        },
                        timeout=10.0,
                    )
                    r.raise_for_status()
                    data = r.json()
                    if data.get("errcode") != 0:
                        logger.error(f"WeCom gettoken error: {data}")
                        return None
                    self._access_token = data["access_token"]
                    # 官方有效期 7200s，提前 5 分钟刷新
                    self._token_expires_at = time.monotonic() + 7200 - 300
                    return self._access_token
            except Exception as e:
                logger.error(f"WeCom gettoken failed: {e}")
                return None

    async def start(self) -> None:
        """保持通道就绪（企业微信仅发送时无需长连）。"""
        self._running = True
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """停止通道."""
        self._running = False
        self._access_token = None

    async def send(self, msg: OutboundMessage) -> None:
        """通过企业微信应用发送文本消息。chat_id 为成员 UserID（或 @all 发全员）。"""
        token = await self._get_token()
        if not token:
            logger.warning("WeCom: no access token, skip send")
            return
        body: dict[str, Any] = {
            "touser": msg.chat_id,
            "msgtype": "text",
            "agentid": self.config.agent_id,
            "text": {"content": msg.content},
        }
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{SEND_URL}?access_token={token}",
                    json=body,
                    timeout=10.0,
                )
                r.raise_for_status()
                data = r.json()
                if data.get("errcode") != 0:
                    logger.error(f"WeCom send error: {data}")
        except Exception as e:
            logger.error(f"WeCom send failed: {e}")
