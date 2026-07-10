"""Config 模块单元测试。"""

from __future__ import annotations

import pytest

from src.config import Config, _parse_bool, _parse_int, _parse_float
from src.models import ConfigError


class TestParseBool:
    def test_empty_returns_default(self) -> None:
        assert _parse_bool("", True, "TEST") is True
        assert _parse_bool("", False, "TEST") is False

    def test_true_variants(self) -> None:
        for v in ("true", "True", "TRUE", "1", "yes", "y", "on"):
            assert _parse_bool(v, False, "TEST") is True

    def test_false_variants(self) -> None:
        for v in ("false", "False", "FALSE", "0", "no", "n", "off"):
            assert _parse_bool(v, True, "TEST") is False

    def test_invalid_returns_default(self) -> None:
        assert _parse_bool("maybe", True, "TEST") is True
        assert _parse_bool("xxx", False, "TEST") is False


class TestParseInt:
    def test_empty_returns_default(self) -> None:
        assert _parse_int("", 42, "TEST") == 42

    def test_valid_value(self) -> None:
        assert _parse_int("5", 3, "TEST") == 5

    def test_out_of_range(self) -> None:
        assert _parse_int("100", 3, "TEST", min_val=0, max_val=10) == 3

    def test_not_integer(self) -> None:
        assert _parse_int("abc", 3, "TEST") == 3


class TestParseFloat:
    def test_empty_returns_default(self) -> None:
        assert _parse_float("", 3.14, "TEST") == 3.14

    def test_valid_value(self) -> None:
        assert _parse_float("2.5", 1.0, "TEST") == 2.5

    def test_out_of_range(self) -> None:
        assert _parse_float("100.0", 1.0, "TEST", min_val=0, max_val=10.0) == 1.0


class TestConfig:
    def test_missing_cookies_raises_config_error(self, clean_env: None) -> None:
        with pytest.raises(ConfigError, match="GLADOS_COOKIES"):
            Config()

    def test_empty_cookies_raises_config_error(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GLADOS_COOKIES", "&&&")
        with pytest.raises(ConfigError, match="有效 Cookie"):
            Config()

    def test_minimal_config(self, minimal_env: dict[str, str]) -> None:
        cfg = Config()
        assert len(cfg.cookies_list) == 1
        assert cfg.cookies_list[0] == "koa:sess=test123"
        assert cfg.domains == ("glados.cloud",)
        assert cfg.exchange_plan == "plan500"
        assert cfg.exchange_points == 500
        assert cfg.verbose is False
        assert cfg.push_channel == ""
        assert cfg.push_token == ""
        assert cfg.retry_max == 3
        assert cfg.retry_backoff == 2.0

    def test_multi_cookie_config(self, multi_cookie_env: None) -> None:
        cfg = Config()
        assert len(cfg.cookies_list) == 3
        assert cfg.cookies_list == ["c1", "c2", "c3"]
        assert cfg.exchange_plan == "plan200"
        assert cfg.exchange_points == 200
        assert cfg.verbose is True
        assert cfg.push_channel == "bark"
        assert cfg.push_token == "testkey123"
        assert cfg.retry_max == 5

    def test_custom_domains(
        self, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GLADOS_DOMAINS", "foo.com, bar.org")
        cfg = Config()
        assert cfg.domains == ("foo.com", "bar.org")

    def test_invalid_exchange_plan_falls_back(
        self, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GLADOS_EXCHANGE_PLAN", "plan999")
        cfg = Config()
        assert cfg.exchange_plan == "plan500"