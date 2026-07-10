"""Push 模块单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.push import (
    create_pusher,
    send_push,
    CHANNEL_BARK,
    CHANNEL_TELEGRAM,
    CHANNEL_SERVERCHAN,
    CHANNEL_PUSHPLUS,
    CHANNEL_WECOM,
    CHANNEL_FEISHU,
    CHANNEL_NONE,
    SUPPORTED_CHANNELS,
)


class TestCreatePusher:
    def test_none_channel_returns_none(self) -> None:
        assert create_pusher("none", "token") is None
        assert create_pusher("", "token") is None

    def test_unknown_channel_returns_none(self) -> None:
        assert create_pusher("discord", "token") is None

    def test_empty_token_returns_none(self) -> None:
        assert create_pusher(CHANNEL_BARK, "") is None
        assert create_pusher(CHANNEL_BARK, "  ") is None

    def test_valid_bark(self) -> None:
        pusher = create_pusher(CHANNEL_BARK, "mykey123")
        assert pusher is not None
        assert pusher.token == "mykey123"

    def test_valid_telegram(self) -> None:
        pusher = create_pusher(CHANNEL_TELEGRAM, "bot123:abc@123456")
        assert pusher is not None
        assert pusher.token == "bot123:abc@123456"

    def test_valid_serverchan(self) -> None:
        pusher = create_pusher(CHANNEL_SERVERCHAN, "SCT12345")
        assert pusher is not None

    def test_valid_pushplus(self) -> None:
        pusher = create_pusher(CHANNEL_PUSHPLUS, "token123")
        assert pusher is not None

    def test_valid_wecom(self) -> None:
        pusher = create_pusher(CHANNEL_WECOM, "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc")
        assert pusher is not None

    def test_valid_feishu(self) -> None:
        pusher = create_pusher(CHANNEL_FEISHU, "https://open.feishu.cn/open-apis/bot/v2/hook/uuid")
        assert pusher is not None


class TestBarkPusher:
    def test_send_success(self) -> None:
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_get.return_value = mock_resp

            result = send_push(CHANNEL_BARK, "key123", "Test Title", "Test Body")
            assert result is True
            mock_get.assert_called_once()

    def test_send_failure(self) -> None:
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_resp.status_code = 500
            mock_get.return_value = mock_resp

            result = send_push(CHANNEL_BARK, "key123", "Test", "Body")
            assert result is False


class TestTelegramPusher:
    def test_bad_token_format(self) -> None:
        """缺少 chat_id 时不应发送。"""
        result = send_push(CHANNEL_TELEGRAM, "bot123:abc", "Title", "Body")
        assert result is False

    def test_send_success(self) -> None:
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_post.return_value = mock_resp

            result = send_push(
                CHANNEL_TELEGRAM,
                "bot123:abc@123456",
                "Title",
                "Body",
            )
            assert result is True