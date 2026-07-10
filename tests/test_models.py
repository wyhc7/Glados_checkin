"""Models 模块单元测试。"""

from __future__ import annotations

from src.constants import CheckinStatus
from src.models import (
    CheckinResult,
    Summary,
    ConfigError,
    NetworkError,
    GladosError,
    CheckinRejected,
)


class TestExceptions:
    def test_hierarchy(self) -> None:
        """验证异常继承关系。"""
        assert issubclass(ConfigError, GladosError)
        assert issubclass(NetworkError, GladosError)
        assert issubclass(CheckinRejected, GladosError)

    def test_catch_by_base(self) -> None:
        """子类可被基类捕获。"""
        try:
            raise ConfigError("test")
        except GladosError:
            pass  # 预期行为


class TestCheckinResult:
    def test_default_values(self) -> None:
        r = CheckinResult(cookie_index=1, domain="x.com")
        assert r.status == "签到失败"
        assert r.points == "0"
        assert r.days == "None"
        assert r.points_total == "None"
        assert r.exchange == "未兑换"
        assert r.code == CheckinStatus.FAILURE

    def test_is_success(self) -> None:
        r = CheckinResult(cookie_index=1, domain="x.com", code=CheckinStatus.SUCCESS)
        assert r.is_success is True
        assert r.is_repeat is False

    def test_is_repeat(self) -> None:
        r = CheckinResult(cookie_index=1, domain="x.com", code=CheckinStatus.REPEAT)
        assert r.is_repeat is True
        assert r.is_success is False


class TestSummary:
    def test_empty(self) -> None:
        s = Summary()
        assert s.success_count == 0
        assert s.repeat_count == 0
        assert s.fail_count == 0
        assert s.title == "GLaDOS 签到 | ✅成功0 ❌失败0 🔄重复0"

    def test_counts(self) -> None:
        results = [
            CheckinResult(1, "a.com", code=CheckinStatus.SUCCESS),
            CheckinResult(1, "b.com", code=CheckinStatus.SUCCESS),
            CheckinResult(2, "a.com", code=CheckinStatus.REPEAT),
            CheckinResult(2, "b.com", code=CheckinStatus.FAILURE),
        ]
        s = Summary(results=results)
        assert s.success_count == 2
        assert s.repeat_count == 1
        assert s.fail_count == 1

    def test_format_lines(self) -> None:
        results = [
            CheckinResult(1, "glados.cloud", status="签到成功", points="10",
                          days="30 天", points_total="100 积分",
                          exchange="兑换成功: plan500",
                          code=CheckinStatus.SUCCESS),
        ]
        s = Summary(results=results)
        lines = s.format_lines()
        assert len(lines) == 1
        assert "glados.cloud" not in lines[0]  # 行中不含 domain 字段
        assert "获10分" in lines[0]
        assert "余30 天" in lines[0]

    def test_push_content(self) -> None:
        results = [
            CheckinResult(1, "glados.cloud", status="签到成功", points="8",
                          days="59 天", points_total="59 积分",
                          exchange="兑换失败: 积分不足",
                          code=CheckinStatus.SUCCESS),
            CheckinResult(2, "glados.cloud", status="重复签到", points="0",
                          days="60 天", points_total="60 积分",
                          exchange="兑换失败: 积分不足",
                          code=CheckinStatus.REPEAT),
        ]
        s = Summary(results=results)
        content = s.push_content
        assert "✅ 账号1" in content
        assert "🔄 账号2" in content
        assert "剩余：59 天" in content
        assert "累计 59 积分" in content
        assert "\n\n" in content  # 多段分隔

    def test_content(self) -> None:
        results = [
            CheckinResult(1, "a.com", code=CheckinStatus.SUCCESS),
            CheckinResult(2, "b.com", code=CheckinStatus.FAILURE),
        ]
        s = Summary(results=results)
        content = s.content
        assert content.startswith("#1")
        assert "#2" in content