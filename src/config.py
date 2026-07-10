"""配置管理：从环境变量加载并校验。"""

from __future__ import annotations

import os
import logging
from typing import Final

from .constants import EXCHANGE_PLAN_POINTS, L
from .models import ConfigError

logger = logging.getLogger(__name__)

# ── 默认值 ────────────────────────────────────────────────
DEFAULT_EXCHANGE_PLAN: Final = "plan500"
DEFAULT_VERBOSE: Final = False
DEFAULT_DOMAINS: Final = ("glados.cloud",)
DEFAULT_RETRY_MAX: Final = 3
DEFAULT_RETRY_BACKOFF: Final = 2.0  # 秒

# 环境变量键名
_ENV_PUSH_CHANNEL = "GLADOS_PUSH_CHANNEL"   # 推送渠道: telegram|bark|serverchan|pushplus|wecom|feishu
_ENV_PUSH_TOKEN = "GLADOS_PUSH_TOKEN"        # 推送 token/key/URL
_ENV_COOKIES = "GLADOS_COOKIES"
_ENV_EXCHANGE_PLAN = "GLADOS_EXCHANGE_PLAN"
_ENV_VERBOSE = "GLADOS_VERBOSE"
_ENV_DOMAINS = "GLADOS_DOMAINS"              # 自定义域名，逗号分隔
_ENV_RETRY_MAX = "GLADOS_RETRY_MAX"
_ENV_RETRY_BACKOFF = "GLADOS_RETRY_BACKOFF"


class Config:
    """不可变配置对象：构造后所有字段只读。"""

    def __init__(self) -> None:
        # ── Cookies ──
        raw = os.environ.get(_ENV_COOKIES, "")
        if not raw.strip():
            raise ConfigError(
                f"环境变量 '{_ENV_COOKIES}' 未设置或为空。"
                "请在 GitHub Secrets 中配置 GLADOS_COOKIES。"
            )
        self.cookies_list: Final[list[str]] = [
            c.strip() for c in raw.split("&") if c.strip()
        ]
        if not self.cookies_list:
            raise ConfigError(
                f"环境变量 '{_ENV_COOKIES}' 已设置但未包含有效 Cookie。"
                "格式: cookie1&cookie2&cookie3"
            )

        # ── 域名 ──
        domains_env = os.environ.get(_ENV_DOMAINS, "")
        if domains_env.strip():
            self.domains: Final[tuple[str, ...]] = tuple(
                d.strip() for d in domains_env.split(",") if d.strip()
            )
        else:
            self.domains = DEFAULT_DOMAINS

        # ── 兑换计划 ──
        plan = os.environ.get(_ENV_EXCHANGE_PLAN, DEFAULT_EXCHANGE_PLAN)
        if plan not in EXCHANGE_PLAN_POINTS:
            logger.warning(
                f"{L.WARNING} '{_ENV_EXCHANGE_PLAN}' 值 '{plan}' 无效，"
                f"回退到 {DEFAULT_EXCHANGE_PLAN}"
            )
            plan = DEFAULT_EXCHANGE_PLAN
        self.exchange_plan: Final[str] = plan
        self.exchange_points: Final[int] = EXCHANGE_PLAN_POINTS[plan]

        # ── Verbose ──
        verbose_env = os.environ.get(_ENV_VERBOSE, "")
        self.verbose: Final[bool] = _parse_bool(
            verbose_env, DEFAULT_VERBOSE, _ENV_VERBOSE
        )

        # ── 重试参数 ──
        self.retry_max: Final[int] = _parse_int(
            os.environ.get(_ENV_RETRY_MAX, ""),
            DEFAULT_RETRY_MAX,
            _ENV_RETRY_MAX,
            min_val=0,
            max_val=10,
        )
        self.retry_backoff: Final[float] = _parse_float(
            os.environ.get(_ENV_RETRY_BACKOFF, ""),
            DEFAULT_RETRY_BACKOFF,
            _ENV_RETRY_BACKOFF,
            min_val=0.5,
            max_val=30.0,
        )

        # ── 推送 ──
        self.push_channel: Final[str] = os.environ.get(
            _ENV_PUSH_CHANNEL, ""
        ).strip().lower()
        self.push_token: Final[str] = os.environ.get(
            _ENV_PUSH_TOKEN, ""
        ).strip()

        # ── 日志摘要 ──
        logger.info(
            f"{L.INFO} Cookies: {len(self.cookies_list)} 个 | "
            f"域名: {self.domains} | 兑换计划: {self.exchange_plan}"
            f"({self.exchange_points}分) | 重试: {self.retry_max}次"
        )
        if self.push_channel:
            logger.info(
                f"{L.PUSH} 推送渠道: {self.push_channel}"
            )
        else:
            logger.info(f"{L.INFO} 未配置推送渠道。")


# ── 工具函数 ──────────────────────────────────────────────
def _parse_bool(raw: str, default: bool, env_key: str) -> bool:
    """解析布尔型环境变量。"""
    if not raw:
        return default
    low = raw.lower()
    if low in ("true", "1", "yes", "y", "on"):
        return True
    if low in ("false", "0", "no", "n", "off"):
        return False
    logger.warning(
        f"{L.WARNING} '{env_key}' 值 '{raw}' 无法解析，使用默认值 {default}"
    )
    return default


def _parse_int(
    raw: str, default: int, env_key: str, min_val: int = 0, max_val: int = 100
) -> int:
    """解析整数型环境变量。"""
    if not raw:
        return default
    try:
        val = int(raw)
        if not (min_val <= val <= max_val):
            logger.warning(
                f"{L.WARNING} '{env_key}'={val} 超出范围 [{min_val},{max_val}]，"
                f"使用默认值 {default}"
            )
            return default
        return val
    except ValueError:
        logger.warning(
            f"{L.WARNING} '{env_key}' 值 '{raw}' 不是整数，使用默认值 {default}"
        )
        return default


def _parse_float(
    raw: str, default: float, env_key: str, min_val: float = 0.0, max_val: float = 60.0
) -> float:
    """解析浮点型环境变量。"""
    if not raw:
        return default
    try:
        val = float(raw)
        if not (min_val <= val <= max_val):
            logger.warning(
                f"{L.WARNING} '{env_key}'={val} 超出范围 [{min_val},{max_val}]，"
                f"使用默认值 {default}"
            )
            return default
        return val
    except ValueError:
        logger.warning(
            f"{L.WARNING} '{env_key}' 值 '{raw}' 不是数字，使用默认值 {default}"
        )
        return default