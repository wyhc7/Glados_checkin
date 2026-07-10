"""常量定义：枚举、API 端点、Emoji。"""

from __future__ import annotations

from enum import Enum


# ── 签到状态 ──────────────────────────────────────────────
class CheckinStatus(Enum):
    SUCCESS = 0
    REPEAT = 1
    FAILURE = -2


# ── 兑换计划 ──────────────────────────────────────────────
class ExchangePlan(Enum):
    PLAN100 = "plan100"
    PLAN200 = "plan200"
    PLAN500 = "plan500"


EXCHANGE_PLAN_POINTS: dict[str, int] = {
    ExchangePlan.PLAN100.value: 100,
    ExchangePlan.PLAN200.value: 200,
    ExchangePlan.PLAN500.value: 500,
}


# ── API 端点 ──────────────────────────────────────────────
class APIEndpoint(Enum):
    CHECKIN = "/api/user/checkin"
    STATUS = "/api/user/status"
    POINTS = "/api/user/points"
    EXCHANGE = "/api/user/exchange"


# ── Emoji ─────────────────────────────────────────────────
class L:
    """日志 Emoji 常量。类名 L = LogEmoji 缩写。"""

    SUCCESS = "✅"
    FAIL = "❌"
    REPEAT = "🔄"
    PENDING = "⏳"
    CHECKIN = "🎫"
    STATUS = "📊"
    POINTS = "💰"
    EXCHANGE = "🎁"
    START = "🚀"
    END = "🏁"
    COOKIE = "🍪"
    DOMAIN = "🌐"
    PUSH = "📡"
    WARNING = "⚠️"
    ERROR = "🔴"
    INFO = "ℹ️"
    RETRY = "🔁"