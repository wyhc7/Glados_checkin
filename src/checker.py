"""签到编排器：逐个 Cookie × Domain 执行签到流程。"""

from __future__ import annotations

import logging
from typing import Any

from .api import APIClient
from .config import Config
from .constants import EXCHANGE_PLAN_DAYS, EXCHANGE_PLAN_POINTS, CheckinStatus, L
from .models import CheckinResult, Summary, GladosError

logger = logging.getLogger(__name__)


def pick_best_plan(points: int) -> tuple[str, int, int] | None:
    """在积分能承受的范围内，选出兑到天数最多的计划。

    规则是"只用一次兑换、换最长天数"，不追求把积分花光：
        900 分 → plan500（100 天）
        450 分 → plan200（30 天，plan500 换不起）
        150 分 → plan100（10 天）
        50  分 → None（啥也换不起）

    返回 ``(plan, 消耗积分, 获得天数)``；一个都换不起时返回 None。
    """
    best: tuple[str, int, int] | None = None
    for plan, need in EXCHANGE_PLAN_POINTS.items():
        if points < need:
            continue
        days = EXCHANGE_PLAN_DAYS.get(plan, 0)
        # 天数更多者优先；天数相同则消耗更少者优先
        if best is None or days > best[2] or (days == best[2] and need < best[1]):
            best = (plan, need, days)
    return best


class Checker:
    """签到编排器：遍历 cookies × domains，依次完成签到/查询/兑换。"""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.results: list[CheckinResult] = []
        self.summary = Summary()

    def run(self) -> Summary:
        """执行所有签到任务，返回 Summary。"""
        cookie_count = len(self.config.cookies_list)
        domain_count = len(self.config.domains)
        total = cookie_count * domain_count

        logger.info(
            f"{L.INFO} 共 {cookie_count} Cookie × {domain_count} 域名 "
            f"= {total} 个任务"
        )

        task_idx = 0
        for cookie_idx, cookie in enumerate(self.config.cookies_list, 1):
            logger.info(
                f"{L.START} {'=' * 10} Cookie {cookie_idx}/{cookie_count} {'=' * 10}"
            )

            for domain in self.config.domains:
                task_idx += 1
                logger.info(
                    f"{L.INFO} --- 任务 {task_idx}/{total}: "
                    f"{L.COOKIE}[{cookie_idx}] @ {L.DOMAIN}[{domain}] ---"
                )

                result = self._process_one(cookie, cookie_idx, domain)
                self.results.append(result)

                if result.is_success:
                    logger.info(
                        f"{L.SUCCESS} 结果: {result.status}, "
                        f"获 {result.points} 积分, 余 {result.days}, "
                        f"总 {result.points_total}, {result.exchange}"
                    )
                else:
                    logger.warning(
                        f"{L.WARNING} 结果: {result.status}"
                    )

        self.summary = Summary(results=self.results)
        return self.summary

    def _process_one(
        self,
        cookie: str,
        cookie_idx: int,
        domain: str,
    ) -> CheckinResult:
        """处理单个 cookie+domain 的完整签到流程。"""
        result = CheckinResult(cookie_index=cookie_idx, domain=domain)

        with APIClient(
            domain=domain,
            cookie_index=cookie_idx,
            verbose=self.config.verbose,
            retry_max=self.config.retry_max,
            retry_backoff=self.config.retry_backoff,
        ) as api:
            try:
                # 1. 查询剩余天数
                logger.info(
                    f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                    f"{L.STATUS} 查询剩余天数"
                )
                days_str, _ = api.get_status(cookie)
                result.days = days_str

                # 2. 签到
                logger.info(
                    f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                    f"{L.CHECKIN} 执行签到"
                )
                try:
                    checkin_resp = api.checkin(cookie)
                    result.status = checkin_resp["status"]
                    result.code = checkin_resp.get("code", CheckinStatus.FAILURE)
                    result.points = checkin_resp.get("points", "0")
                except GladosError as e:
                    logger.warning(
                        f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                        f"{L.WARNING} 签到异常: {e}"
                    )
                    result.status = f"签到失败: {e}"
                    result.code = CheckinStatus.FAILURE

                # 3. 查询总积分
                logger.info(
                    f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                    f"{L.POINTS} 查询总积分"
                )
                try:
                    points_str, points_num = api.get_points(cookie)
                    result.points_total = points_str
                except GladosError as e:
                    points_num = 0
                    logger.warning(
                        f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                        f"{L.WARNING} 查询积分失败: {e}"
                    )

                # 4. 积分兑换
                # 规则：只在快到期（剩余 < exchange_min_days）时才换，
                # 且换"积分能承受的最长天数"，不做多次兑换。
                left = api.left_days
                if left is None:
                    result.exchange = "跳过兑换（剩余天数未知）"
                    logger.info(
                        f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                        f"{L.EXCHANGE} {result.exchange}"
                    )
                elif left >= self.config.exchange_min_days:
                    result.exchange = (
                        f"跳过兑换（余 {left} 天，"
                        f"≥{self.config.exchange_min_days} 天不换）"
                    )
                    logger.info(
                        f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                        f"{L.EXCHANGE} {result.exchange}"
                    )
                else:
                    best = pick_best_plan(points_num)
                    if best is None:
                        cheapest = min(EXCHANGE_PLAN_POINTS.values())
                        result.exchange = (
                            f"无法兑换（余 {left} 天，"
                            f"{points_num} 分不足最低 {cheapest} 分）"
                        )
                        logger.warning(
                            f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                            f"{L.WARNING} {result.exchange}"
                        )
                    else:
                        plan, need, days = best
                        logger.info(
                            f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                            f"{L.EXCHANGE} 余 {left} 天，{points_num} 分 "
                            f"→ 兑换 {plan}（{need} 分 / {days} 天）"
                        )
                        try:
                            result.exchange = api.exchange(cookie, plan, need)
                        except GladosError as e:
                            logger.warning(
                                f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                                f"{L.WARNING} 兑换异常: {e}"
                            )
                            result.exchange = f"兑换失败: {e}"

            except GladosError as e:
                logger.error(
                    f"{L.COOKIE}[{cookie_idx}] {L.DOMAIN}[{domain}] "
                    f"{L.ERROR} 流程中断: {e}"
                )
                result.status = f"流程中断: {e}"
                result.code = CheckinStatus.FAILURE

        return result