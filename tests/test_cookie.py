"""cookie 清洗 / 自检 / 域名探测 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.cookie import (
    clean_cookie,
    cookie_flavor,
    cookie_keys,
    mask_cookie,
    probe_domain,
    validate_cookie,
)
from src.models import AuthError, NetworkError


class TestCookieFlavor:
    def test_detects_gld(self) -> None:
        assert cookie_flavor("gld:sess=abc; gld:sess.sig=def") == "gld"

    def test_detects_koa(self) -> None:
        assert cookie_flavor("koa:sess=abc; koa:sess.sig=def") == "koa"

    def test_unknown(self) -> None:
        assert cookie_flavor("foo=bar") is None


class TestCleanCookie:
    def test_strips_cookie_prefix(self) -> None:
        assert (
            clean_cookie("Cookie: koa:sess=abc; koa:sess.sig=def")
            == "koa:sess=abc; koa:sess.sig=def"
        )

    def test_strips_quotes_and_newlines(self) -> None:
        raw = '"koa:sess=abc;\nkoa:sess.sig=def"\n'
        assert clean_cookie(raw) == "koa:sess=abc; koa:sess.sig=def"

    def test_collapses_spaces(self) -> None:
        assert (
            clean_cookie("  koa:sess=abc ;   koa:sess.sig=def  ")
            == "koa:sess=abc; koa:sess.sig=def"
        )

    def test_idempotent(self) -> None:
        once = clean_cookie('Cookie: "koa:sess=a; koa:sess.sig=b"')
        assert clean_cookie(once) == once


class TestCookieKeys:
    def test_extracts_keys(self) -> None:
        assert cookie_keys("koa:sess=abc; koa:sess.sig=def") == [
            "koa:sess",
            "koa:sess.sig",
        ]

    def test_ignores_garbage(self) -> None:
        assert cookie_keys(";;=;koa:sess=abc;") == ["koa:sess"]


class TestValidateCookie:
    def test_complete_cookie_is_clean(self) -> None:
        assert validate_cookie("koa:sess=abc; koa:sess.sig=def") == []

    def test_gld_complete_cookie_is_clean(self) -> None:
        assert validate_cookie("gld:sess=abc; gld:sess.sig=def") == []

    def test_missing_sig_warns(self) -> None:
        warnings = validate_cookie("koa:sess=abc")
        assert any("sess.sig" in w for w in warnings)

    def test_gld_missing_sig_warns(self) -> None:
        warnings = validate_cookie("gld:sess=abc")
        assert any("sess.sig" in w for w in warnings)

    def test_mixed_flavors_warns(self) -> None:
        warnings = validate_cookie("gld:sess=a; gld:sess.sig=b; koa:sess=c; koa:sess.sig=d")
        assert any("两套字段名" in w for w in warnings)

    def test_empty_warns(self) -> None:
        assert validate_cookie("   ")

    def test_label_in_message(self) -> None:
        warnings = validate_cookie("koa:sess=abc", label="Cookie1")
        assert warnings and warnings[0].startswith("[Cookie1]")


class TestMaskCookie:
    def test_hides_values(self) -> None:
        masked = mask_cookie("koa:sess=abcdefgh; koa:sess.sig=ijklmnop")
        assert "abcdefgh" not in masked
        assert "abcd***" in masked
        assert "ijkl***" in masked

    def test_short_value_fully_masked(self) -> None:
        assert mask_cookie("koa:sess=abc") == "koa:sess=***"


def _fake_client(codes: dict[str, int], net_errors: set[str] | None = None):
    """构造 APIClient 替身：按域名返回不同 code。"""
    net_errors = net_errors or set()

    def factory(domain: str, **_kw: object) -> MagicMock:
        api = MagicMock()
        api.__enter__.return_value = api
        api.__exit__.return_value = False
        if domain in net_errors:
            api.raw_status_code.side_effect = NetworkError("boom")
        else:
            api.raw_status_code.return_value = codes.get(domain, -2)
        return api

    return factory


class TestProbeDomain:
    def test_returns_first_working_domain(self) -> None:
        factory = _fake_client({"glados.cloud": -2, "glados.rocks": 0})
        with patch("src.api.APIClient", side_effect=factory):
            domain, code = probe_domain(
                "koa:sess=a; koa:sess.sig=b",
                ("glados.cloud", "glados.rocks"),
            )
        assert (domain, code) == ("glados.rocks", 0)

    def test_skips_network_errors(self) -> None:
        factory = _fake_client({"glados.work": 0}, net_errors={"glados.cloud"})
        with patch("src.api.APIClient", side_effect=factory):
            domain, _ = probe_domain(
                "koa:sess=a; koa:sess.sig=b", ("glados.cloud", "glados.work")
            )
        assert domain == "glados.work"

    def test_all_fail_raises_auth_error(self) -> None:
        factory = _fake_client({})
        with patch("src.api.APIClient", side_effect=factory):
            with pytest.raises(AuthError) as ei:
                probe_domain("koa:sess=a; koa:sess.sig=b", ("glados.cloud", "glados.rocks"))
        assert "koa:sess.sig" in str(ei.value) or "code=-2" in str(ei.value)
