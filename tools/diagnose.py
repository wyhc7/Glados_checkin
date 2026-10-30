"""本地排查工具：一条命令定位 code=-2 到底卡在哪。

用法::

    python -m tools.diagnose                 # 读 GLADOS_COOKIES / .env
    python -m tools.diagnose --local
    python -m tools.diagnose --cookie 'koa:sess=...; koa:sess.sig=...'
    python -m tools.diagnose --proxy http://127.0.0.1:7890

它做三件事：
  1. 打印出口 IP（判断是不是机房/被风控的 IP）；
  2. 校验 cookie 结构（缺 sig 直接指出）；
  3. 逐个域名打 /api/user/status，输出每个域名的 code。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 允许 `python tools/diagnose.py` 直接跑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api import APIClient  # noqa: E402
from src.constants import DEFAULT_DOMAINS  # noqa: E402
from src.cookie import (  # noqa: E402
    clean_cookie,
    cookie_flavor,
    mask_cookie,
    validate_cookie,
)
from src.models import NetworkError  # noqa: E402


def _public_ip(proxy: str | None) -> str:
    import requests

    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        return requests.get(
            "https://api.ipify.org", timeout=10, proxies=proxies
        ).text.strip()
    except Exception as e:  # noqa: BLE001
        return f"<获取失败: {e}>"


def _load_cookies(args: argparse.Namespace) -> list[str]:
    if args.cookie:
        return [clean_cookie(args.cookie)]
    if args.local:
        try:
            from dotenv import load_dotenv  # type: ignore

            env_path = Path(__file__).resolve().parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                print(f"[dotenv] 已加载 {env_path}")
        except ImportError:
            print("[dotenv] 未安装 python-dotenv，跳过")
    raw = os.environ.get("GLADOS_COOKIES", "")
    if not raw.strip():
        print("❌ 未提供 cookie：用 --cookie 或设置 GLADOS_COOKIES / .env")
        raise SystemExit(1)
    return [clean_cookie(c) for c in raw.replace("\n", "&").split("&") if c.strip()]


def main() -> int:
    p = argparse.ArgumentParser(description="GLaDOS 签到问题诊断")
    p.add_argument(
        "--cookie",
        help="单条 cookie（gld:sess + gld:sess.sig，老版 koa:sess 也支持）",
    )
    p.add_argument("--local", action="store_true", help="从 .env 读取配置")
    p.add_argument("--proxy", help="测试代理，如 http://127.0.0.1:7890")
    p.add_argument(
        "--domains",
        default=",".join(DEFAULT_DOMAINS),
        help="要探测的域名，逗号分隔",
    )
    args = p.parse_args()

    domains = tuple(d.strip() for d in args.domains.split(",") if d.strip())

    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy

    print("=" * 60)
    print(f"出口 IP: {_public_ip(args.proxy)}")
    print("=" * 60)

    cookies = _load_cookies(args)
    print(f"共 {len(cookies)} 条 cookie\n")

    ok_total = 0
    for idx, ck in enumerate(cookies, 1):
        print(f"── Cookie {idx} ── {mask_cookie(ck)}")
        problems = validate_cookie(ck, label=f"Cookie{idx}")
        if problems:
            for w in problems:
                print(f"  ⚠️  {w}")
        else:
            print(f"  ✅ 结构完整（{cookie_flavor(ck) or '?'}:sess + 签名段）")

        winner = None
        for domain in domains:
            try:
                with APIClient(domain=domain) as api:
                    code = api.raw_status_code(ck)
            except NetworkError as e:
                print(f"  🌐 {domain:<16} 网络错误: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                print(f"  🌐 {domain:<16} 异常: {type(e).__name__}: {e}")
                continue
            flag = "✅" if code == 0 else "❌"
            print(f"  🌐 {domain:<16} code={code} {flag}")
            if code == 0 and winner is None:
                winner = domain

        if winner:
            ok_total += 1
            print(f"  → 可用域名: {winner}\n")
        else:
            print("  → 全部域名 code=-2：cookie 已失效或 IP 被风控，请重抓/换 IP\n")

    print("=" * 60)
    print(f"结果: {ok_total}/{len(cookies)} 条 cookie 可用")
    if ok_total == 0:
        print("结论: 先去无痕窗口重新登录 GLaDOS，复制 gld:sess + gld:sess.sig 两段；")
        print("      再确认出口 IP 不是机房段（可加 --proxy 对比）。")
        return 2
    print("结论: cookie 有效，直接用 `python -m src.main --local` 跑签到。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
