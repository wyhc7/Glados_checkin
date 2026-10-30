"""Cookie 清洗与域名探测。

GLaDOS 用 koa-session，``koa:sess`` + ``koa:sess.sig`` 必须成对出现；
手动从浏览器复制时常见的三种污染——带 ``Cookie:`` 前缀、带引号、带换行——
都会让服务端解析不出 session，一律回 ``code=-2 没有权限``。
另外 session 跟域名绑定，写死一个域名很容易撞上 ``-2``，
所以这里提供 ``probe_domain`` 先用最小代价把可用域名试出来。
"""

from __future__ import annotations

import logging
import re
from typing import Final

from .models import AuthError

logger = logging.getLogger(__name__)

#: 默认探测顺序：glados.cloud 是国内最常用入口，其余为备选/历史域名。
DEFAULT_PROBE_DOMAINS: Final[tuple[str, ...]] = (
    "glados.cloud",
    "glados.rocks",
    "glados.work",
    "glados.space",
    "glados.la",
)

_PREFIX_RE = re.compile(r"^\s*(cookie\s*:\s*)", re.IGNORECASE)
_KV_RE = re.compile(r"^\s*([A-Za-z0-9_.:%-]+)\s*=\s*(.*)$")


def clean_cookie(raw: str) -> str:
    """清洗单条 cookie 字符串。

    处理：
      1. 去掉 ``Cookie:`` 前缀、首尾引号、换行/回车/制表符；
      2. 去掉每段 key/value 内部的换行，并压掉多余空格；
      3. 若缺少 ``koa:sess.sig``，保留原样（由 ``validate_cookie`` 报警）。

    >>> clean_cookie('Cookie: koa:sess=abc; koa:sess.sig=def')
    'koa:sess=abc; koa:sess.sig=def'
    """
    s = raw.strip().strip('"').strip("'")
    s = s.replace("\r", "").replace("\n", "").replace("\t", "")
    s = _PREFIX_RE.sub("", s)
    parts = [p.strip() for p in s.split(";") if p.strip()]
    return "; ".join(parts)


def cookie_keys(cookie: str) -> list[str]:
    """解析 cookie 字符串里的 key 列表（用于自检）。"""
    keys: list[str] = []
    for part in cookie.split(";"):
        m = _KV_RE.match(part.strip())
        if m:
            keys.append(m.group(1))
    return keys


def validate_cookie(cookie: str, label: str = "") -> list[str]:
    """自检 cookie 结构，返回人类可读的告警列表（不抛异常）。"""
    warnings: list[str] = []
    tag = f"[{label}] " if label else ""
    if not cookie.strip():
        warnings.append(f"{tag}cookie 为空")
        return warnings

    keys = cookie_keys(cookie)
    if not any(k == "koa:sess" for k in keys):
        warnings.append(f"{tag}缺少 'koa:sess'，当前 keys={keys}")
    if not any(k == "koa:sess.sig" for k in keys):
        warnings.append(
            f"{tag}缺少 'koa:sess.sig'（签名段），服务端会直接回 code=-2"
        )
    if " " in cookie.split("=", 1)[-1]:
        # value 中出现裸空格，多半是复制时吞进了换行残留
        warnings.append(f"{tag}cookie 值含空格，可能已被截断")
    return warnings


def mask_cookie(cookie: str) -> str:
    """打日志用的脱敏形式：只保留每个 value 的前 4 位。"""
    out: list[str] = []
    for part in cookie.split(";"):
        part = part.strip()
        m = _KV_RE.match(part)
        if not m:
            continue
        k, v = m.group(1), m.group(2)
        out.append(f"{k}={v[:4]}***" if len(v) > 4 else f"{k}=***")
    return "; ".join(out)


def probe_domain(
    cookie: str,
    domains: tuple[str, ...] = DEFAULT_PROBE_DOMAINS,
    *,
    verbose: bool = False,
) -> tuple[str, int]:
    """依次探测域名，返回 (可用域名, status_code)。

    判定标准：``/api/user/status`` 回 ``code == 0``。
    全部失败时抛 ``AuthError`` —— 说明 cookie 本身在所有域名下都失效，
    继续跑下去没有意义。
    """
    # 延迟导入，避免 api ↔ cookie 循环依赖
    from .api import APIClient
    from .models import NetworkError

    reasons: list[str] = []
    for domain in domains:
        try:
            with APIClient(domain=domain) as api:
                code = api.raw_status_code(cookie)
        except NetworkError as e:
            reasons.append(f"{domain}: 网络错误 {e}")
            continue
        except Exception as e:  # noqa: BLE001 - 探测阶段吞掉一切，只要结果
            reasons.append(f"{domain}: {type(e).__name__} {e}")
            continue

        if verbose:
            logger.info("探测 %s → code=%s", domain, code)
        if code == 0:
            return domain, code
        reasons.append(f"{domain}: code={code}")

    raise AuthError(
        "Cookie 在所有域名下均无权限（code=-2）。"
        "请在无痕窗口重新登录 GLaDOS 后重抓 koa:sess 与 koa:sess.sig。\n  "
        + "\n  ".join(reasons)
    )
