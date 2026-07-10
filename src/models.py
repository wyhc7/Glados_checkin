"""自定义异常与数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from .constants import CheckinStatus


# ── 自定义异常 ────────────────────────────────────────────
class GladosError(Exception):
    """基础异常，所有 GLaDOS 相关异常由此派生。"""


class ConfigError(GladosError):
    """配置错误：缺少必要环境变量或值无效。"""


class NetworkError(GladosError):
    """网络请求失败（含超时、DNS、连接重置等）。"""


class AuthError(GladosError):
    """认证失败：Cookie 无效或过期。"""


class CheckinRejected(GladosError):
    """签到被拒绝（code != 0 且 != 1）。"""


# ── 数据模型 ──────────────────────────────────────────────
@dataclass
class CheckinResult:
    """单次签到结果。"""

    cookie_index: int
    domain: str
    status: str = "签到失败"
    points: str = "0"
    days: str = "None"
    points_total: str = "None"
    exchange: str = "未兑换"
    code: CheckinStatus = CheckinStatus.FAILURE

    @property
    def is_success(self) -> bool:
        return self.code == CheckinStatus.SUCCESS

    @property
    def is_repeat(self) -> bool:
        return self.code == CheckinStatus.REPEAT


@dataclass
class Summary:
    """签到汇总。"""

    results: list[CheckinResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.is_success)

    @property
    def repeat_count(self) -> int:
        return sum(1 for r in self.results if r.is_repeat)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.is_success and not r.is_repeat)

    @property
    def title(self) -> str:
        return (
            f"GLaDOS 签到 | ✅成功{self.success_count} "
            f"❌失败{self.fail_count} 🔄重复{self.repeat_count}"
        )

    def format_lines(self) -> list[str]:
        """生成人类可读的结果行列表。"""
        lines: list[str] = []
        for i, r in enumerate(self.results, 1):
            line = (
                f"#{i} | P:{r.points} | 剩余:{r.days} | "
                f"总积分:{r.points_total} | {r.status} | {r.exchange}"
            )
            lines.append(line)
        return lines

    @property
    def content(self) -> str:
        return "\n".join(self.format_lines())