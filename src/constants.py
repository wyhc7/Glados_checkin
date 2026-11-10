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
#: 来源：Devilstore/Glados-Railgun-checkin 的 CANDIDATE_DOMAINS。
#: railgun.info 是迁移后的新站，glados-facility.com 是备用域。
DEFAULT_DOMAINS: Final = (
    "glados.cloud",
    "railgun.info",
    "glados.network",
    "glados.rocks",
    "glados.one",
    "glados.space",
    "glados.vip",
    "glados-facility.com",
)

#: session 字段名。GLaDOS 换过后端：
#:   新版（2024 后）：gld:sess / gld:sess.sig
#:   老版（koa-session）：koa:sess / koa:sess.sig
#: 服务端只认自己那套，字段名对不上 = 匿名访问 = code=-2。
SESSION_KEYS: Final = ("gld:sess", "koa:sess")
SESSION_SIG_KEYS: Final = ("gld:sess.sig", "koa:sess.sig")


# ── API 端点 ──────────────────────────────────────────────
class APIEndpoint(Enum):
    CHECKIN = "/api/user/checkin"
    CHECKIN_CHALLENGE = "/api/user/checkin/challenge"
    STATUS = "/api/user/status"
    POINTS = "/api/user/points"
    EXCHANGE = "/api/user/exchange"


# ── 签到 challenge（2026-11 新增，缺了它只能拿 1 分）──────
#: proof = sha256(f"{nonce}.{suffix}")
CHALLENGE_SUFFIX: Final = "glados-observe-v1"
#: 拿到 nonce 后必须等待的秒数，早提交会被判无效
CHALLENGE_DELAY_SECONDS: Final = 2.5

# ── 设备校验 ──────────────────────────────────────────────
#: 签到返回 code=4 且 reason=device-mismatch 时，按 loginDevice 换 UA 重试。
#: 版本号无关紧要，平台 token（Windows/iPhone/Android…）才是关键。
PLATFORM_UA: dict[str, str] = {
    "Windows": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "macOS": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Linux": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "iPhone": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "iOS": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Android": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
}


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