"""常量定义：枚举、API 端点、Emoji。"""

from __future__ import annotations

from enum import Enum
from typing import Final


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

#: 各计划兑换到的天数（与 /api/user/points 返回的 plans 字段一致）。
#: 用于"积分够换多个计划时，选能换到的最长天数"。
EXCHANGE_PLAN_DAYS: dict[str, int] = {
    ExchangePlan.PLAN100.value: 10,
    ExchangePlan.PLAN200.value: 30,
    ExchangePlan.PLAN500.value: 100,
}

#: 剩余天数低于该值才触发兑换（默认 7 天）
DEFAULT_EXCHANGE_MIN_DAYS: Final = 7

#: 域名探测顺序：按国内可达性排列，命中一个即停止。
#: 优先级来源：GitHub 上 Glados-Railgun-checkin / GLaDOS_Checkin_ql 的实践。
DEFAULT_DOMAINS: Final = (
    "glados.cloud",
    "glados.rocks",
    "glados.work",
    "glados.space",
)


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