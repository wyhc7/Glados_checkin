"""签到降权诊断：分辨「只有 1 分」到底是 IP 还是别的原因。

原理：签到只发一次，所以不能反复试——但可以在签到**之前**做对照：

  1. 打印当前出口 IP，并判断它是不是机房/云厂商段；
  2. 用 curl_cffi 的 Chrome 指纹访问一次站点，看是否被 CF 拦截；
  3. 用 --proxy 换一个出口再跑一遍，对比两次 IP 是否不同。

真正判断依据是：同一天用不同出口签到，分数不同 → 就是 IP 问题。

用法::

    python -m tools.diagnose_weight              # 看当前出口
    python -m tools.diagnose_weight --proxy http://127.0.0.1:7890
"""

from __future__ import annotations

import argparse
import ipaddress
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api import _HAS_CFFI, _impersonate_target  # noqa: E402

#: 常见云厂商/机房 ASN 关键词，命中说明大概率会被风控降权
_DATACENTER_HINTS = (
    "microsoft",
    "azure",
    "amazon",
    "aws",
    "google",
    "digitalocean",
    "linode",
    "vultr",
    "hetzner",
    "ovh",
    "oracle",
    "alibaba",
    "aliyun",
    "tencent",
    "cloudflare",
    "github",
    "fastly",
    "leaseweb",
    "contabo",
)


def _fetch_json(url: str, proxy: str | None) -> dict:
    if _HAS_CFFI:
        from curl_cffi import requests as cffi

        return cffi.get(url, impersonate=_impersonate_target(), timeout=20).json()
    import requests

    proxies = {"http": proxy, "https": proxy} if proxy else None
    return requests.get(url, timeout=20, proxies=proxies).json()


def main() -> int:
    p = argparse.ArgumentParser(description="GLaDOS 签到降权（1 分）诊断")
    p.add_argument("--proxy", help="对比用代理，如 http://127.0.0.1:7890")
    args = p.parse_args()

    import os

    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
        os.environ["ALL_PROXY"] = args.proxy

    print("=" * 62)
    print(f"TLS 伪装: {'开 (' + _impersonate_target() + ')' if _HAS_CFFI else '关（未安装 curl_cffi）'}")
    print("=" * 62)

    try:
        info = _fetch_json("https://ipinfo.io/json", args.proxy)
    except Exception as e:  # noqa: BLE001
        print(f"❌ 取出口信息失败: {e}")
        return 1

    ip = info.get("ip", "?")
    org = (info.get("org") or "").lower()
    city = info.get("city", "?")
    country = info.get("country", "?")
    print(f"出口 IP : {ip}")
    print(f"归属    : {org or '未知'} / {city}, {country}")

    hits = [h for h in _DATACENTER_HINTS if h in org]
    if hits:
        print(f"⚠️  判断  : 机房/云厂商段（命中 {', '.join(hits)}）")
        print("          → 这类 IP 极可能被 GLaDOS 降权到 1 分")
        print("          → 用 --proxy 指向家里的出口再测一次做对比")
    else:
        print("✅ 判断  : 看起来不是常见机房段")

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        print("   （IP 格式异常，可能是代理返回了错误页）")

    print("-" * 62)
    print("下一步：")
    print("  1. 在家里网络下跑本命令，记下 IP 和判断结果；")
    print("  2. 明天在**家里出口**跑一次签到（GLADOS_PROXY 指向家里）；")
    print("  3. 若家里出口能签出十几分，就确定是 IP 降权。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
