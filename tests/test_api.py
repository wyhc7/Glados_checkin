"""API 模块单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api import APIClient, _clean_api_message
from src.constants import APIEndpoint, CheckinStatus
from src.models import NetworkError, CheckinRejected


def _make_mock_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code < 400
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestAPIClientConstruction:
    def test_init_defaults(self) -> None:
        api = APIClient("test.domain")
        assert api.domain == "test.domain"
        assert api.cookie_index == 0
        assert api.verbose is False
        assert api._session is None  # 延迟创建

    def test_context_manager_closes(self) -> None:
        with APIClient("test.domain") as api:
            api.session  # 触发创建
        assert api._session is None  # __exit__ 调用了 close


class TestAPIClientCheckin:
    def test_checkin_success(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {"code": 0, "points": 15, "message": "ok"}
        )

        result = api.checkin("fake_cookie")
        assert result["code"] == CheckinStatus.SUCCESS
        assert result["points"] == "15"
        assert result["status"] == "签到成功"

    def test_checkin_repeat(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {"code": 1, "message": "already checked in"}
        )

        result = api.checkin("fake_cookie")
        assert result["code"] == CheckinStatus.REPEAT
        assert result["status"] == "重复签到"

    def test_checkin_rejected_raises(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {"code": -1, "message": "invalid token"}
        )

        with pytest.raises(CheckinRejected):
            api.checkin("fake_cookie")

    def test_checkin_network_error_raises(self) -> None:
        """模拟网络错误场景。"""
        api = APIClient("test.domain", retry_max=0)
        api._session = MagicMock()
        api._session.post.side_effect = NetworkError("连接失败")

        with pytest.raises(NetworkError):
            api.checkin("fake_cookie")


class TestAPIClientStatus:
    def test_get_status_returns_days(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.get.return_value = _make_mock_response(
            200, {"code": 0, "data": {"leftDays": "30.5"}}
        )

        days_str, code = api.get_status("fake_cookie")
        assert days_str == "30 天"
        assert code == 0

    def test_get_status_none_days(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.get.return_value = _make_mock_response(
            200, {"code": -1, "data": {}}
        )

        days_str, code = api.get_status("fake_cookie")
        assert days_str == "None 天"


class TestAPIClientPoints:
    def test_get_points_returns_value(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.get.return_value = _make_mock_response(
            200, {"code": 0, "points": 350}
        )

        points_str, points_num = api.get_points("fake_cookie")
        assert points_str == "350 积分"
        assert points_num == 350

    def test_get_points_none(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.get.return_value = _make_mock_response(
            200, {"code": -1}
        )

        points_str, points_num = api.get_points("fake_cookie")
        assert points_str == "None 积分"
        assert points_num == 0


class TestAPIClientExchange:
    def test_exchange_success(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {"code": 0, "message": "兑换成功"}
        )

        result = api.exchange("fake_cookie", "plan500", 500)
        assert result == "兑换成功: plan500"

    def test_exchange_failure(self) -> None:
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {"code": -1, "message": "积分不足"}
        )

        result = api.exchange("fake_cookie", "plan500", 500)
        assert "兑换失败" in result

    def test_exchange_clean_floating_message(self) -> None:
        """验证浮点精度尾数被清理。"""
        api = APIClient("test.domain")
        api._session = MagicMock()
        api._session.post.return_value = _make_mock_response(
            200, {
                "code": -1,
                "message": "Not enough points. Need 200, have 59.0000000000000000",
            }
        )

        result = api.exchange("fake_cookie", "plan200", 200)
        assert "59.000000" not in result
        assert "have 59" in result.lower()


class TestCleanApiMessage:
    def test_removes_floating_tail(self) -> None:
        assert _clean_api_message("have 59.0000000000000000") == "have 59"
        assert _clean_api_message("100.0000") == "100"

    def test_preserves_normal_floats(self) -> None:
        assert _clean_api_message("12.5") == "12.5"
        assert _clean_api_message("3.14") == "3.14"

    def test_preserves_non_number_text(self) -> None:
        assert _clean_api_message("兑换成功") == "兑换成功"