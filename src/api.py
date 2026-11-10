"""HTTP API 客户端：重试、超时、结构化日志。

请求层优先用 ``curl_cffi``（伪造 Chrome 的 TLS/JA3 指纹）。
GLaDOS 会按客户端指纹给不同奖励：真浏览器签到拿十几分，
requests 这种"塑料 Chrome"只有 1 分。装不上 curl_cffi 时自动退回 requests，
功能不受影响，只是可能被降权到 1 分。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import (
    APIEndpoint,
    CHALLENGE_DELAY_SECONDS,
    CHALLENGE_SUFFIX,
    PLATFORM_UA,
    CheckinStatus,
    L,
)
from .models import AuthError, NetworkError, CheckinRejected

#: curl_cffi 可选依赖：有则用（TLS 指纹更像真浏览器），无则退回 requests
try:
    from curl_cffi import requests as cffi_requests

    _HAS_CFFI = True
except Exception:  # pragma: no cover - 环境相关
    cffi_requests = None  # type: ignore[assignment]
    _HAS_CFFI = False


# ── 工具 ──────────────────────────────────────────────────
def _clean_api_message(msg: str) -> str:
    """清理 API 返回消息中的浮点精度尾数，如 59.0000000000000000 → 59。"""
    return re.sub(r'(\d+)\.0{4,}', r'\1', msg)

logger = logging.getLogger(__name__)

# ── HTTP 配置 ──────────────────────────────────────────────
# 国内到 glados 的握手偶发较慢，实测 6s 左右，30s 给足余量。
_CONNECT_TIMEOUT = 30
_READ_TIMEOUT = 30
#: 域名探测用短超时：多个候选域名逐个试，长超时会叠加成几分钟。
_PROBE_TIMEOUT = (8, 12)
#: 默认 UA 与默认 sec-ch-ua 必须严格配套，否则服务端一眼看穿。
#: 这里对齐真实抓包（Edge 157 / Chromium 157 / Windows），
#: 需要换浏览器时同时改这两处，或用 GLADOS_USER_AGENT 整体覆盖。
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0"
)

_DEFAULT_SEC_CH_UA = (
    '"Not-A.Brand";v="99", "Microsoft Edge";v="157", "Chromium";v="157"'
)


def _user_agent() -> str:
    """User-Agent：优先用 GLADOS_USER_AGENT，否则用默认值。

    GLaDOS 会校验 UA 与登录设备是否一致（code=4 / device-mismatch），
    所以最好填成抓 cookie 那个浏览器的 UA。
    """
    return os.environ.get("GLADOS_USER_AGENT", "").strip() or _DEFAULT_UA


def _sec_ch_ua() -> str:
    """sec-ch-ua 客户端提示头，需与 UA 平台/版本一致。"""
    return os.environ.get("GLADOS_SEC_CH_UA", "").strip() or _DEFAULT_SEC_CH_UA


_USER_AGENT = _DEFAULT_UA

#: 模拟浏览器请求头，取值对齐真实抓包。
_BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "priority": "u=1, i",
}

#: curl_cffi 的指纹别名。可用 GLADOS_IMPERSONATE 覆盖（如 chrome124/chrome131）。
_DEFAULT_IMPERSONATE = "chrome124"


def _impersonate_target() -> str:
    return os.environ.get("GLADOS_IMPERSONATE", "").strip() or _DEFAULT_IMPERSONATE


class APIClient:
    """GLaDOS API 客户端：对一个 domain + cookie 的操作集。"""

    def __init__(
        self,
        domain: str,
        cookie_index: int = 0,
        verbose: bool = False,
        retry_max: int = 3,
        retry_backoff: float = 2.0,
        user_agent: str = "",
    ) -> None:
        self.domain = domain
        self.cookie_index = cookie_index
        self.verbose = verbose
        self.retry_max = retry_max
        self.retry_backoff = retry_backoff
        #: 该账号专属 UA（抓 cookie 时的浏览器）；空则用 GLADOS_USER_AGENT 或默认值
        self.user_agent = (user_agent or "").strip()
        #: 探测模式：使用更短超时，避免多域名叠加成几分钟
        self._probing = False
        self._session: requests.Session | None = None
        self._cffi_session: Any | None = None
        #: 最近一次 get_status 拿到的剩余天数（None 表示未知）
        self.left_days: int | None = None

    @property
    def ua(self) -> str:
        """本会话生效的 User-Agent。"""
        return self.user_agent or _user_agent()

    @property
    def uses_tls_impersonation(self) -> bool:
        """是否启用了 curl_cffi 的 TLS 指纹伪装。"""
        return _HAS_CFFI

    @property
    def session(self) -> requests.Session:
        """延迟创建 Session，避免每次用完再新建。"""
        if self._session is None:
            self._session = requests.Session()

            # urllib3 层重试（仅覆盖连接/读超时 + 特定状态码）
            # 注意：只让 GET 自动重放。签到/兑换是 POST，被 urllib3 在 5xx 时
            # 自动重试会造成重复提交；POST 的重试统一交给应用层显式控制。
            retry_strategy = Retry(
                total=self.retry_max,
                backoff_factor=self.retry_backoff / 3,  # urllib3 backoff 乘算
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
                raise_on_status=False,
            )
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=2,
                pool_maxsize=4,
            )
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)

            self._session.headers.update(
                {
                    "Origin": f"https://{self.domain}",
                    "Referer": f"https://{self.domain}/console/checkin",
                    "User-Agent": self.ua,
                    "Content-Type": "application/json; charset=utf-8",
                    **_BROWSER_HEADERS,
                    "sec-ch-ua": _sec_ch_ua(),
                }
            )
        return self._session

    @property
    def cffi_session(self) -> Any:
        """curl_cffi 会话：带 Chrome TLS 指纹，优先于 requests 使用。"""
        if self._cffi_session is None:
            self._cffi_session = cffi_requests.Session(impersonate=_impersonate_target())
            self._cffi_session.headers.update(
                {
                    "Origin": f"https://{self.domain}",
                    "Referer": f"https://{self.domain}/console/checkin",
                    "User-Agent": self.ua,
                    "Content-Type": "application/json; charset=utf-8",
                    **_BROWSER_HEADERS,
                    "sec-ch-ua": _sec_ch_ua(),
                }
            )
        return self._cffi_session

    def prewarm(self, cookie: str) -> None:
        """模拟真人的访问序列：首页 → 控制台 → 签到页。

        GLaDOS 对"直接打 API、从没访问过任何页面"的会话更容易判自动化，
        而且要拿到页面下发的 cookie/埋点。失败不阻断主流程。
        """
        for path in ("/", "/console", "/console/checkin"):
            try:
                self._request_page(f"https://{self.domain}{path}", cookie)
                time.sleep(1.2)  # 别让三个请求挤在同一毫秒
            except Exception:  # noqa: BLE001 - 预热失败不阻断
                continue

    def close(self) -> None:
        for sess in (self._session, self._cffi_session):
            if sess is not None:
                try:
                    sess.close()
                except Exception:
                    pass
        self._session = None
        self._cffi_session = None

    def __enter__(self) -> APIClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # ── 日志 ────────────────────────────────────────────────
    def _log(self, emoji: str, msg: str, *, force: bool = False) -> None:
        if force or self.verbose:
            logger.info(
                f"{L.COOKIE}[{self.cookie_index}] "
                f"{L.DOMAIN}[{self.domain}] {emoji} {msg}"
            )

    def _warn(self, msg: str) -> None:
        logger.warning(
            f"{L.COOKIE}[{self.cookie_index}] "
            f"{L.DOMAIN}[{self.domain}] {L.WARNING} {msg}"
        )

    # ── 底层请求 ────────────────────────────────────────────
    def _url(self, endpoint: APIEndpoint) -> str:
        return f"https://{self.domain}{endpoint.value}"

    def _send(
        self,
        url: str,
        *,
        method: str,
        headers: dict[str, str],
        body: dict[str, str] | None = None,
    ) -> Any:
        """发一次请求。

        默认走 requests（普通 TLS）：curl_cffi 伪造的 TLS 指纹在国内部分网络
        会被直接阻断（curl 28 超时），可靠性优先。
        需要伪装指纹时设 ``GLADOS_TLS_IMPERSONATE=1`` 改用 curl_cffi，
        且失败会自动回退 requests。
        """
        payload = json.dumps(body) if body else None
        timeout = (
            _PROBE_TIMEOUT
            if self._probing
            else (_CONNECT_TIMEOUT, _READ_TIMEOUT)
        )
        use_cffi = _HAS_CFFI and os.environ.get(
            "GLADOS_TLS_IMPERSONATE", ""
        ).strip().lower() in ("1", "true", "yes", "on")

        if use_cffi:
            try:
                if method == "GET":
                    return self.cffi_session.get(
                        url, headers=headers, timeout=timeout
                    )
                return self.cffi_session.post(
                    url, headers=headers, data=payload, timeout=timeout
                )
            except Exception as e:  # noqa: BLE001 - TLS 被阻断时回退
                if not getattr(self, "_cffi_broken", False):
                    self._cffi_broken = True
                    self._warn(f"curl_cffi 请求失败，回退 requests: {type(e).__name__}")

        if method == "GET":
            return self.session.get(url, headers=headers, timeout=timeout)
        return self.session.post(
            url, headers=headers, data=payload, timeout=timeout
        )

    def _request_page(self, url: str, cookie: str) -> None:
        """访问一个 HTML 页面（预热用），忽略响应体。"""
        headers = {
            "Cookie": cookie,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
        }
        self._send(url, method="GET", headers=headers)

    def _request(
        self,
        endpoint: APIEndpoint,
        *,
        method: str = "GET",
        cookie: str,
        body: dict[str, str] | None = None,
        retry: bool = True,
    ) -> Any:
        """发送请求，应用层兜底重试。

        ``retry=False`` 时只发一次（签到/兑换这类非幂等 POST 用），
        避免 5xx 时重复提交。
        """
        url = self._url(endpoint)
        session_headers = {"Cookie": cookie}

        max_attempts = self.retry_max + 1 if retry else 1
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):  # 1 次初始 + N 次重试
            try:
                resp = self._send(
                    url, method=method, headers=session_headers, body=body
                )

                # 5xx 视为瞬时故障，触发重试
                if resp.status_code >= 500:
                    self._warn(f"{url} → {resp.status_code}（第{attempt}次尝试）")
                    if attempt < max_attempts:
                        sleep_s = self.retry_backoff * (2 ** (attempt - 1))
                        time.sleep(sleep_s)
                        continue

                resp.raise_for_status()
                return resp

            except Exception as e:  # 统一按异常类型分流，兼容两套库
                last_exc = e
                name = type(e).__name__
                is_timeout = "Timeout" in name
                is_conn = "Connection" in name
                is_http = "HTTPError" in name and getattr(e, "response", None) is not None

                if is_timeout:
                    self._warn(f"{url} 超时（第{attempt}次尝试）")
                elif is_conn:
                    self._warn(f"{url} 连接失败（第{attempt}次尝试）")
                elif is_http:
                    status = e.response.status_code
                    # 4xx（非 429）不重试，直接抛出
                    if 400 <= status < 500 and status != 429:
                        text = e.response.text[:500]
                        raise NetworkError(f"{url} HTTP {status}: {text}") from e
                    self._warn(f"{url} HTTP 错误（第{attempt}次尝试）")
                else:
                    self._warn(f"{url} 请求异常: {name}: {e}")

            if attempt < max_attempts:
                sleep_s = self.retry_backoff * (2 ** (attempt - 1))
                self._log(L.RETRY, f"将在 {sleep_s:.1f}s 后重试...", force=True)
                time.sleep(sleep_s)

        raise NetworkError(
            f"{url} 请求失败，已重试 {max_attempts - 1} 次"
        ) from last_exc

    # ── 业务操作 ────────────────────────────────────────────
    def raw_status_code(self, cookie: str) -> int:
        """只取 ``/api/user/status`` 的 ``code``，异常一律转成 -2。

        域名探测专用：不发业务日志、不抛 AuthError，方便批量试域名。
        """
        try:
            resp = self._request(
                APIEndpoint.STATUS, method="GET", cookie=cookie, retry=False
            )
            return int(resp.json().get("code", -2))
        except NetworkError:
            raise
        except Exception:
            return -2

    # ── 签到 challenge ──────────────────────────────────────
    def _fetch_challenge(self, cookie: str) -> tuple[str, str] | None:
        """取签到 challenge，返回 (nonce, proof)；取不到返回 None。

        2026-11 起 GLaDOS 在签到前要求这一步：先拿 nonce，等几秒，
        再提交 ``sha256(f"{nonce}.glados-observe-v1")`` 作为 proof。
        跳过它直接按旧协议 POST，会被判为自动化、只给 1 积分。
        """
        try:
            resp = self._request(
                APIEndpoint.CHECKIN_CHALLENGE, method="GET", cookie=cookie, retry=True
            )
            data = resp.json()
        except Exception as e:  # noqa: BLE001 - 取不到就回退旧协议
            logger.warning(
                f"{L.COOKIE}[{self.cookie_index}] {L.DOMAIN}[{self.domain}] "
                f"{L.WARNING} 签到 challenge 获取失败，回退旧协议（可能只拿 1 分）: {e}"
            )
            return None

        if not isinstance(data, dict) or data.get("code") != 0:
            logger.warning(
                f"{L.COOKIE}[{self.cookie_index}] {L.DOMAIN}[{self.domain}] "
                f"{L.WARNING} 签到 challenge 响应异常，回退旧协议: {data}"
            )
            return None

        nonce = data.get("nonce")
        if not nonce:
            logger.warning(
                f"{L.COOKIE}[{self.cookie_index}] {L.DOMAIN}[{self.domain}] "
                f"{L.WARNING} 签到 challenge 缺少 nonce，回退旧协议"
            )
            return None

        # 服务端要求拿到 nonce 后等一会儿再提交，立刻提交视为无效
        time.sleep(CHALLENGE_DELAY_SECONDS)
        proof = hashlib.sha256(
            f"{nonce}.{CHALLENGE_SUFFIX}".encode()
        ).hexdigest()
        # 这是判断"能否拿满积分"的关键一步，必须无条件可见
        logger.info(
            f"{L.COOKIE}[{self.cookie_index}] {L.DOMAIN}[{self.domain}] "
            f"{L.INFO} 已获取签到 challenge（nonce={str(nonce)[:8]}…）"
        )
        return str(nonce), proof

    def _post_checkin(
        self, cookie: str, payload: dict[str, Any], *, as_json: bool
    ) -> dict[str, Any]:
        """发签到 POST。challenge 流程要发 JSON，旧协议发表单。

        非幂等：只发一次，不做任何自动重试。
        """
        url = self._url(APIEndpoint.CHECKIN)
        headers = {
            "Cookie": cookie,
            "Referer": f"https://{self.domain}/console/checkin",
            "Origin": f"https://{self.domain}",
        }
        if as_json:
            headers["Content-Type"] = "application/json; charset=utf-8"
            raw = json.dumps(payload)
        else:
            raw = "&".join(f"{k}={v}" for k, v in payload.items())

        timeout = (_CONNECT_TIMEOUT, _READ_TIMEOUT)
        use_cffi = _HAS_CFFI and os.environ.get(
            "GLADOS_TLS_IMPERSONATE", ""
        ).strip().lower() in ("1", "true", "yes", "on")

        if use_cffi:
            try:
                resp = self.cffi_session.post(
                    url, headers=headers, data=raw, timeout=timeout
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001 - TLS 被阻断时回退
                self._warn(f"curl_cffi 签到失败，回退 requests: {type(e).__name__}")

        resp = self.session.post(url, headers=headers, data=raw, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _earned_points(data: dict[str, Any]) -> str:
        """本次签到所得积分。

        顶层 ``points`` 是账户总积分而非本次所得；本次得分在
        ``list[0].change`` 里。取不到时退回顶层值。
        """
        records = data.get("list")
        if isinstance(records, list) and records and isinstance(records[0], dict):
            change = records[0].get("change")
            if change is not None:
                return str(change)
        return str(data.get("points", 0))

    def checkin(self, cookie: str) -> dict[str, Any]:
        """执行签到。返回 {'code':..., 'points':..., 'message':..., 'status':...}。

        优先走 challenge 流程（正常给十几分）；
        challenge 拿不到时回退旧协议（通常只给 1 分，会打告警）。
        遇到 ``code=4 / device-mismatch`` 时按 ``loginDevice`` 换 UA 重试一次。
        """
        self._log(L.CHECKIN, "执行签到")

        challenge = self._fetch_challenge(cookie)
        if challenge:
            nonce, proof = challenge
            payload: dict[str, Any] = {
                "token": self.domain,
                "nonce": nonce,
                "proof": proof,
            }
        else:
            payload = {"token": self.domain}

        data = self._post_checkin(cookie, payload, as_json=bool(challenge))

        # 设备不匹配：服务端会告诉我们登录设备是什么平台，据此换 UA 再来一次
        if (
            isinstance(data, dict)
            and data.get("code") == 4
            and data.get("reason") == "device-mismatch"
        ):
            device = str(data.get("loginDevice") or "")
            retry_ua = PLATFORM_UA.get(device)
            if retry_ua:
                self._warn(f"设备平台不匹配（loginDevice={device}），按该平台 UA 重试")
                saved_ua = _USER_AGENT
                try:
                    self._override_ua(retry_ua)
                    data = self._post_checkin(
                        cookie, payload, as_json=bool(challenge)
                    )
                finally:
                    self._override_ua(saved_ua)
            else:
                self._warn(
                    f"设备平台不匹配（loginDevice={device}，不在已知列表），"
                    "可设 GLADOS_USER_AGENT 为抓 cookie 那个浏览器的 UA"
                )

        code = data.get("code", -2)
        message = data.get("message", "")
        points = self._earned_points(data) if code == 0 else "0"

        if code == CheckinStatus.SUCCESS.value:
            self._log(L.SUCCESS, f"code={code} points={points} msg={message}")
            # 1 分 = 大概率没走 challenge 或被降权，明确告警
            try:
                if float(points) <= 1:
                    self._warn(
                        f"仅获 {points} 分，疑似被降权"
                        f"（challenge={'已用' if challenge else '未取得'}）"
                    )
            except (TypeError, ValueError):
                pass
            return {
                "code": CheckinStatus.SUCCESS,
                "points": points,
                "message": message,
                "status": "签到成功",
            }
        if code == CheckinStatus.REPEAT.value:
            self._log(L.REPEAT, f"code={code} msg={message}", force=True)
            return {
                "code": CheckinStatus.REPEAT,
                "points": "0",
                "message": message,
                "status": "重复签到",
            }
        # 其他 code → 抛出异常而非返回假成功
        # code=-2 是 GLaDOS 的"没有权限"，本质是 Cookie 失效/被顶掉，
        # 用 AuthError 区分出来，让上层能明确提示"请重抓 Cookie"。
        if code == -2 or "权限" in message or "permission" in message.lower():
            raise AuthError(f"Cookie 失效或无权访问 code={code} msg={message}")
        raise CheckinRejected(f"签到被拒绝 code={code} msg={message}")

    def _override_ua(self, ua: str) -> None:
        """临时替换会话的 User-Agent（设备重试用）。"""
        for sess in (self._session, self._cffi_session):
            if sess is not None:
                try:
                    sess.headers["User-Agent"] = ua
                except Exception:  # noqa: BLE001
                    pass

    def get_status(self, cookie: str) -> tuple[str, int]:
        """获取剩余天数。返回 (天数描述, code)。

        同时把数值存进 ``self.left_days``，供兑换判断用（无需拆字符串）。
        """
        self._log(L.STATUS, "查询剩余天数")
        # status 只用于展示，偶发读超时很常见；只重试 1 次，
        # 避免 3 次 × 30s 把整轮拖上两分钟。
        saved_retry, self.retry_max = self.retry_max, min(self.retry_max, 1)
        try:
            resp = self._request(
                APIEndpoint.STATUS, method="GET", cookie=cookie
            )
        finally:
            self.retry_max = saved_retry
        data = resp.json()
        code = data.get("code", -2)
        left_days = data.get("data", {}).get("leftDays")

        # 结构探测：-2 且没有数据 → 不是"还没签到"，而是 session 不被承认
        if code == -2 and left_days is None:
            raise AuthError(
                f"Cookie 失效或无权访问 code={code} msg={data.get('message', '')}"
            )

        if left_days is not None:
            days_int = int(float(left_days))
            self.left_days: int | None = days_int
            self._log(L.SUCCESS, f"code={code} leftDays={days_int}天")
            return f"{days_int} 天", code
        self.left_days = None
        self._log(L.FAIL, f"code={code} leftDays=None", force=True)
        return "None 天", code

    def get_points(self, cookie: str) -> tuple[str, int]:
        """获取总积分。返回 (积分描述, 积分数值)。"""
        self._log(L.POINTS, "查询总积分")
        resp = self._request(
            APIEndpoint.POINTS, method="GET", cookie=cookie
        )
        data = resp.json()
        code = data.get("code", -2)
        points = data.get("points")

        if code == -2 and points is None:
            raise AuthError(
                f"Cookie 失效或无权访问 code={code} msg={data.get('message', '')}"
            )

        if points is not None:
            points_int = int(float(points))
            self._log(L.SUCCESS, f"code={code} points={points_int}")
            return f"{points_int} 积分", points_int
        self._log(L.FAIL, f"code={code} points=None", force=True)
        return "None 积分", 0

    def exchange(self, cookie: str, plan: str, required_points: int) -> str:
        """积分兑换。返回结果描述字符串。"""
        self._log(
            L.EXCHANGE,
            f"{plan}（需 {required_points} 积分）",
        )
        resp = self._request(
            APIEndpoint.EXCHANGE,
            method="POST",
            cookie=cookie,
            body={"planType": plan},
            retry=False,  # 兑换非幂等，重复提交会重复扣分
        )
        data = resp.json()
        code = data.get("code", -2)
        message = _clean_api_message(data.get("message", "未知错误"))

        if code == 0:
            self._log(L.SUCCESS, f"code={code} msg={message}")
            return f"兑换成功: {plan}"
        self._log(L.FAIL, f"code={code} msg={message}", force=True)
        return f"兑换失败: {message}"