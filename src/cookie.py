"""Cookie 清洗、字段名校验与域名探测。

GLaDOS 换过后端，session 字段名跟着变了：

  新版（2024 之后）: ``gld:sess`` + ``gld:sess.sig``
  老版（koa-session）: ``koa:sess`` + ``koa:sess.sig``

服务端只认自己那套，字段名对不上就等于匿名访问，一律回 ``code=-2 没有权限``
——这跟 cookie 有没有过期、IP 有没有被封完全无关。
手动从浏览器复制时另外三种常见污染——带 ``Cookie:`` 前缀、带引号、带换行——
同样会让服务端解析不出 session。

session 还跟域名绑定，写死一个域名容易撞 ``-2``，
所以这里提供 ``probe_domain`` 先用最小代价把可用域名试出来。
"""

from __future__ import annotations

import logging
import re
from typing import Final

from .constants import SESSION_KEYS, SESSION_SIG_KEYS
from .models import AuthError

logger = logging.getLogger(__name__)

#: 默认探测顺序：国内最常用入口在前，其余为备选/历史域名。
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
      3. 不改 key 名、不做 URL decode（签名段含 ``-``/``_``，decode 会弄坏）。

    >>> clean_cookie('Cookie: gld:sess=abc; gld:sess.sig=def')
    'gld:sess=abc; gld:sess.sig=def'
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


def cookie_flavor(cookie: str) -> str | None:
    """判断这条 cookie 属于哪套字段名：``"gld"`` / ``"koa"`` / ``None``。"""
    keys = set(cookie_keys(cookie))
    for name in ("gld", "koa"):
        if f"{name}:sess" in keys:
            return name
    return None


def validate_cookie(cookie: str, label: str = "") -> list[str]:
    """自检 cookie 结构，返回人类可读的告警列表（不抛异常）。"""
    warnings: list[str] = []
    tag = f"[{label}] " if label else ""
    if not cookie.strip():
        warnings.append(f"{tag}cookie 为空")
        return warnings

    keys = cookie_keys(cookie)
    has_sess = any(k in SESSION_KEYS for k in keys)
    has_sig = any(k in SESSION_SIG_KEYS for k in keys)

    if not has_sess:
        warnings.append(
            f"{tag}缺少 session 字段（需要 {' 或 '.join(SESSION_KEYS)}），"
            f"当前 keys={keys}；服务端会当成匿名访问回 code=-2"
        )
    if not has_sig:
        warnings.append(
            f"{tag}缺少签名段（需要 {' 或 '.join(SESSION_SIG_KEYS)}），"
            f"服务端会直接回 code=-2"
        )

    # 两套混用：多半是复制错了，gld 后端不认 koa，反之亦然
    flavors = {k.split(":")[0] for k in keys if k.endswith(":sess")}
    if len(flavors) > 1:
        warnings.append(
            f"{tag}同时出现 {'/'.join(sorted(flavors))} 两套字段名，保留一套即可"
        )

    if not warnings:
        sig_val = ""
        for part in cookie.split(";"):
            m = _KV_RE.match(part.strip())
            if m and m.group(1) in SESSION_SIG_KEYS:
                sig_val = m.group(2).strip()
                break
        if sig_val and (" " in sig_val or sig_val.endswith("=")):
            warnings.append(f"{tag}签名段疑似被截断或含空格")
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

    flavor = cookie_flavor(cookie)
    hint = (
        f"当前字段名识别为 {flavor}:sess"
        if flavor
        else "未识别到任何 session 字段（需要 gld:sess 或 koa:sess）"
    )
    raise AuthError(
        "Cookie 在所有域名下均无权限（code=-2）。"
        f"{hint}。"
        "请无痕窗口重新登录 GLaDOS，把 gld:sess 与 gld:sess.sig 两段都复制。\n  "
        + "\n  ".join(reasons)
    )
