"""pytest 全局 fixtures。"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清除相关的环境变量，确保测试隔离。"""
    for key in (
        "GLADOS_COOKIES",
        "GLADOS_EXCHANGE_PLAN",
        "GLADOS_VERBOSE",
        "GLADOS_DOMAINS",
        "GLADOS_PUSH_CHANNEL",
        "GLADOS_PUSH_TOKEN",
        "GLADOS_RETRY_MAX",
        "GLADOS_RETRY_BACKOFF",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def minimal_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """最小有效环境变量：1 个 cookie。"""
    monkeypatch.setenv("GLADOS_COOKIES", "koa:sess=test123")
    return {"GLADOS_COOKIES": "koa:sess=test123"}


@pytest.fixture
def multi_cookie_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """多 cookie + 完整配置。"""
    monkeypatch.setenv("GLADOS_COOKIES", "c1&c2&c3")
    monkeypatch.setenv("GLADOS_EXCHANGE_PLAN", "plan200")
    monkeypatch.setenv("GLADOS_VERBOSE", "true")
    monkeypatch.setenv("GLADOS_PUSH_CHANNEL", "bark")
    monkeypatch.setenv("GLADOS_PUSH_TOKEN", "testkey123")
    monkeypatch.setenv("GLADOS_RETRY_MAX", "5")


@pytest.fixture
def mock_requests_session() -> Any:
    """返回一个被 Mock 了的 requests.Session 类。"""
    with patch("requests.Session", autospec=True) as mock_cls:
        session_instance = MagicMock()
        mock_cls.return_value = session_instance
        yield mock_cls, session_instance