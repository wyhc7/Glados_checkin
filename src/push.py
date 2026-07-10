"""多渠道推送服务：Telegram / Bark / Server酱 / PushPlus / 企业微信 / 飞书。

通过环境变量 GLADOS_PUSH_CHANNEL 选择渠道，GLADOS_PUSH_TOKEN 配置凭证。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .constants import L

logger = logging.getLogger(__name__)

# 渠道名常量
CHANNEL_TELEGRAM = "telegram"
CHANNEL_BARK = "bark"
CHANNEL_SERVERCHAN = "serverchan"
CHANNEL_PUSHPLUS = "pushplus"
CHANNEL_WECOM = "wecom"
CHANNEL_FEISHU = "feishu"
CHANNEL_NONE = "none"

SUPPORTED_CHANNELS = {
    CHANNEL_TELEGRAM,
    CHANNEL_BARK,
    CHANNEL_SERVERCHAN,
    CHANNEL_PUSHPLUS,
    CHANNEL_WECOM,
    CHANNEL_FEISHU,
}


# ── 抽象基 ─────────────────────────────────────────────────
class _BasePusher:
    """推送器基类。"""

    def __init__(self, token: str) -> None:
        self.token = token

    def send(self, title: str, content: str) -> bool:
        raise NotImplementedError


# ── Telegram Bot ───────────────────────────────────────────
# Token 格式: bot<token>@<chat_id>
# 或直接用 GLADOS_PUSH_TOKEN=bot123456:ABC...@123456789
class TelegramPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        parts = self.token.split("@")
        bot_token = parts[0]
        chat_id = parts[1] if len(parts) > 1 else ""
        if not bot_token or not chat_id:
            logger.error(f"{L.ERROR} Telegram token 格式错误，应为 bot<token>@<chat_id>")
            return False

        text = f"*{title}*\n\n{content}"
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=15,
            )
            if resp.ok:
                logger.info(f"{L.PUSH} Telegram 推送成功")
                return True
            logger.warning(
                f"{L.WARNING} Telegram 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} Telegram 推送异常: {e}")
            return False


# ── Bark ───────────────────────────────────────────────────
# Token 格式: https://api.day.app/<key>  或  <key>
class BarkPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        base = self.token.strip()
        if not base.startswith("http"):
            base = f"https://api.day.app/{base}"
        url = f"{base.rstrip('/')}/{title}/{content}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.ok:
                logger.info(f"{L.PUSH} Bark 推送成功")
                return True
            logger.warning(
                f"{L.WARNING} Bark 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} Bark 推送异常: {e}")
            return False


# ── Server酱 (旧版) ───────────────────────────────────────
# Token 格式: SCT<key>  或  https://sctapi.ftqq.com/<key>.send
class ServerChanPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        key = self.token.strip()
        if key.startswith("http"):
            url = key
        elif key.startswith("SCT"):
            url = f"https://sctapi.ftqq.com/{key}.send"
        else:
            url = f"https://sctapi.ftqq.com/{key}.send"
        try:
            resp = requests.post(
                url,
                data={"title": title, "desp": content},
                timeout=15,
            )
            if resp.ok:
                logger.info(f"{L.PUSH} Server酱 推送成功")
                return True
            logger.warning(
                f"{L.WARNING} Server酱 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} Server酱 推送异常: {e}")
            return False


# ── PushPlus ───────────────────────────────────────────────
# Token 格式: <token>
class PushPlusPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        url = "http://www.pushplus.plus/send"
        try:
            resp = requests.post(
                url,
                json={
                    "token": self.token.strip(),
                    "title": title,
                    "content": content,
                    "template": "txt",
                },
                timeout=15,
            )
            if resp.ok:
                data = resp.json()
                if data.get("code") == 200:
                    logger.info(f"{L.PUSH} PushPlus 推送成功")
                    return True
            logger.warning(
                f"{L.WARNING} PushPlus 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} PushPlus 推送异常: {e}")
            return False


# ── 企业微信机器人 ─────────────────────────────────────────
# Token 格式: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>
class WeComPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        url = self.token.strip()
        if not url.startswith("http"):
            logger.error(f"{L.ERROR} 企业微信 token 应为完整的 Webhook URL")
            return False
        try:
            resp = requests.post(
                url,
                json={
                    "msgtype": "markdown",
                    "markdown": {
                        "content": f"## {title}\n{content}",
                    },
                },
                timeout=15,
            )
            if resp.ok and resp.json().get("errcode") == 0:
                logger.info(f"{L.PUSH} 企业微信 推送成功")
                return True
            logger.warning(
                f"{L.WARNING} 企业微信 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} 企业微信 推送异常: {e}")
            return False


# ── 飞书机器人 ─────────────────────────────────────────────
# Token 格式: https://open.feishu.cn/open-apis/bot/v2/hook/<uuid>
class FeishuPusher(_BasePusher):
    def send(self, title: str, content: str) -> bool:
        url = self.token.strip()
        if not url.startswith("http"):
            logger.error(f"{L.ERROR} 飞书 token 应为完整的 Webhook URL")
            return False
        try:
            resp = requests.post(
                url,
                json={
                    "msg_type": "interactive",
                    "card": {
                        "header": {
                            "title": {"tag": "plain_text", "content": title},
                            "template": "green",
                        },
                        "elements": [
                            {
                                "tag": "markdown",
                                "content": content,
                            }
                        ],
                    },
                },
                timeout=15,
            )
            if resp.ok and resp.json().get("code") == 0:
                logger.info(f"{L.PUSH} 飞书 推送成功")
                return True
            logger.warning(
                f"{L.WARNING} 飞书 推送失败: {resp.status_code} {resp.text[:200]}"
            )
            return False
        except Exception as e:
            logger.error(f"{L.ERROR} 飞书 推送异常: {e}")
            return False


# ── 渠道映射 ───────────────────────────────────────────────
_CHANNEL_MAP: dict[str, type[_BasePusher]] = {
    CHANNEL_TELEGRAM: TelegramPusher,
    CHANNEL_BARK: BarkPusher,
    CHANNEL_SERVERCHAN: ServerChanPusher,
    CHANNEL_PUSHPLUS: PushPlusPusher,
    CHANNEL_WECOM: WeComPusher,
    CHANNEL_FEISHU: FeishuPusher,
}


# ── 公共接口 ───────────────────────────────────────────────
def create_pusher(channel: str, token: str) -> _BasePusher | None:
    """根据渠道名和 token 创建推送器实例。"""
    channel_lower = channel.strip().lower()
    if channel_lower == CHANNEL_NONE or not channel_lower:
        logger.info(f"{L.INFO} 未配置推送渠道，跳过推送。")
        return None
    if channel_lower not in _CHANNEL_MAP:
        logger.warning(
            f"{L.WARNING} 未知推送渠道 '{channel}'，"
            f"支持: {', '.join(sorted(_CHANNEL_MAP))}"
        )
        return None
    if not token.strip():
        logger.warning(
            f"{L.WARNING} 推送渠道 '{channel}' 已配置但 GLADOS_PUSH_TOKEN 为空。"
        )
        return None

    pusher_cls = _CHANNEL_MAP[channel_lower]
    return pusher_cls(token.strip())


def send_push(channel: str, token: str, title: str, content: str) -> bool:
    """便捷函数：创建推送器并发送。"""
    pusher = create_pusher(channel, token)
    if pusher is None:
        return False
    return pusher.send(title, content)