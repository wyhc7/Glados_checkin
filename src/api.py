"""HTTP API 客户端：重试、超时、结构化日志。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import APIEndpoint, CheckinStatus, L
from .models import NetworkError, CheckinRejected

logger = logging.getLogger(__name__)

# ── HTTP 配置 ──────────────────────────────────────────────
_CONNECT_TIMEOUT = 15
_READ_TIMEOUT = 30
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


class APIClient:
    """GLaDOS API 客户端：对一个 domain + cookie 的操作集。"""

    def __init__(
        self,
        domain: str,
        cookie_index: int = 0,
        verbose: bool = False,
        retry_max: int = 3,
        retry_backoff: float = 2.0,
    ) -> None:
        self.domain = domain
        self.cookie_index = cookie_index
        self.verbose = verbose
        self.retry_max = retry_max
        self.retry_backoff = retry_backoff
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        """延迟创建 Session，避免每次用完再新建。"""
        if self._session is None:
            self._session = requests.Session()

            # urllib3 层重试（仅覆盖连接/读超时 + 特定状态码）
            retry_strategy = Retry(
                total=self.retry_max,
                backoff_factor=self.retry_backoff / 3,  # urllib3 backoff 乘算
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
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
                    "User-Agent": _USER_AGENT,
                    "Content-Type": "application/json; charset=utf-8",
                }
            )
        return self._session

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            finally:
                self._session = None

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

    def _request(
        self,
        endpoint: APIEndpoint,
        *,
        method: str = "GET",
        cookie: str,
        body: dict[str, str] | None = None,
    ) -> requests.Response:
        """发送请求，应用层兜底重试。"""
        url = self._url(endpoint)
        session_headers = {"Cookie": cookie}

        last_exc: Exception | None = None
        for attempt in range(1, self.retry_max + 2):  # 1 次初始 + N 次重试
            try:
                if method == "GET":
                    resp = self.session.get(
                        url,
                        headers=session_headers,
                        timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                    )
                elif method == "POST":
                    resp = self.session.post(
                        url,
                        headers=session_headers,
                        data=json.dumps(body) if body else None,
                        timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
                    )
                else:
                    raise ValueError(f"不支持的 HTTP 方法: {method}")

                # 5xx 视为瞬时故障，触发重试
                if resp.status_code >= 500:
                    self._warn(f"{url} → {resp.status_code}（第{attempt}次尝试）")
                    if attempt <= self.retry_max:
                        sleep_s = self.retry_backoff * (2 ** (attempt - 1))
                        time.sleep(sleep_s)
                        continue

                resp.raise_for_status()
                return resp

            except requests.exceptions.Timeout as e:
                last_exc = e
                self._warn(f"{url} 超时（第{attempt}次尝试）")
            except requests.exceptions.ConnectionError as e:
                last_exc = e
                self._warn(f"{url} 连接失败（第{attempt}次尝试）")
            except requests.exceptions.HTTPError as e:
                # 4xx（非 429）不重试，直接抛出
                if (
                    e.response is not None
                    and 400 <= e.response.status_code < 500
                    and e.response.status_code != 429
                ):
                    raise NetworkError(
                        f"{url} HTTP {e.response.status_code}: {e.response.text[:500]}"
                    ) from e
                last_exc = e
                self._warn(f"{url} HTTP 错误（第{attempt}次尝试）")

            if attempt <= self.retry_max:
                sleep_s = self.retry_backoff * (2 ** (attempt - 1))
                self._log(L.RETRY, f"将在 {sleep_s:.1f}s 后重试...", force=True)
                time.sleep(sleep_s)

        raise NetworkError(
            f"{url} 请求失败，已重试 {self.retry_max} 次"
        ) from last_exc

    # ── 业务操作 ────────────────────────────────────────────
    def checkin(self, cookie: str) -> dict[str, Any]:
        """执行签到。返回 {'code':..., 'points':..., 'message':..., 'status':...}。"""
        self._log(L.CHECKIN, "执行签到")
        resp = self._request(
            APIEndpoint.CHECKIN, method="POST", cookie=cookie,
            body={"token": self.domain},
        )
        data = resp.json()
        code = data.get("code", -2)
        message = data.get("message", "")
        points = str(data.get("points", 0))

        if code == CheckinStatus.SUCCESS.value:
            self._log(L.SUCCESS, f"code={code} points={points} msg={message}")
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
        raise CheckinRejected(f"签到被拒绝 code={code} msg={message}")

    def get_status(self, cookie: str) -> tuple[str, int]:
        """获取剩余天数。返回 (天数描述, code)。"""
        self._log(L.STATUS, "查询剩余天数")
        resp = self._request(
            APIEndpoint.STATUS, method="GET", cookie=cookie
        )
        data = resp.json()
        code = data.get("code", -2)
        left_days = data.get("data", {}).get("leftDays")

        if left_days is not None:
            days_int = int(float(left_days))
            self._log(L.SUCCESS, f"code={code} leftDays={days_int}天")
            return f"{days_int} 天", code
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
        )
        data = resp.json()
        code = data.get("code", -2)
        message = data.get("message", "未知错误")

        if code == 0:
            self._log(L.SUCCESS, f"code={code} msg={message}")
            return f"兑换成功: {plan}"
        self._log(L.FAIL, f"code={code} msg={message}", force=True)
        return f"兑换失败: {message}"