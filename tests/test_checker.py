"""Checker 模块单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.constants import CheckinStatus
from src.config import Config
from src.checker import Checker
from src.models import CheckinRejected


def _make_mock_api(**kwargs: object) -> MagicMock:
    """创建带 context manager 支持的 mock API 实例。"""
    mock_api = MagicMock(**kwargs)
    mock_api.__enter__.return_value = mock_api
    mock_api.__exit__.return_value = False
    return mock_api


class TestCheckerRun:
    def test_single_success_flow(
        self, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mock API 返回成功，验证 Checker 正确编排。"""
        monkeypatch.setenv("GLADOS_COOKIES", "test_cookie")
        config = Config()

        mock_api = _make_mock_api(
            get_status=MagicMock(return_value=("30 天", 0)),
            checkin=MagicMock(
                return_value={
                    "code": CheckinStatus.SUCCESS,
                    "points": "10",
                    "message": "ok",
                    "status": "签到成功",
                }
            ),
            get_points=MagicMock(return_value=("100 积分", 100)),
            exchange=MagicMock(return_value="兑换成功: plan500"),
        )

        with patch("src.checker.APIClient", return_value=mock_api):
            checker = Checker(config)
            summary = checker.run()

        assert summary.success_count >= 1  # glados.cloud = 1 个任务
        assert summary.fail_count == 0

    def test_checkin_failure_captured(
        self, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """签到被拒绝时，Checker 不应崩溃，而是记录失败。"""
        monkeypatch.setenv("GLADOS_COOKIES", "bad_cookie")
        config = Config()

        mock_api = _make_mock_api(
            get_status=MagicMock(return_value=("None 天", -2)),
            checkin=MagicMock(side_effect=CheckinRejected("bad token")),
            get_points=MagicMock(return_value=("None 积分", 0)),
            exchange=MagicMock(return_value="兑换失败"),
        )

        with patch("src.checker.APIClient", return_value=mock_api):
            checker = Checker(config)
            summary = checker.run()

        assert summary.success_count == 0
        # 两个域名都失败
        assert summary.fail_count == len(config.domains)  # 1