"""主入口：加载配置 → 执行签到 → 推送通知。

支持两种运行模式：
  1. GitHub Actions（自动从 Secrets 读取环境变量）
  2. 本地测试（通过 --local 标志 + .env 文件或环境变量）

用法:
  python -m src.main          # GitHub Actions 模式
  python -m src.main --local  # 本地模式（读取 .env）
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Config
from .checker import Checker
from .push import send_push
from .models import ConfigError, GladosError
from .constants import L
from .logging_config import init_logger


def _try_load_dotenv() -> None:
    """尝试加载项目根目录的 .env 文件（python-dotenv 可选）。"""
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]

        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print(f"[dotenv] 已加载: {env_path}")
        else:
            print(f"[dotenv] 未找到 .env 文件: {env_path}，将使用系统环境变量")
    except ImportError:
        print("[dotenv] python-dotenv 未安装，将使用系统环境变量")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GLaDOS 自动签到脚本",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="本地运行模式：加载 .env 文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="空跑模式：加载配置但跳过实际签到请求",
    )
    return parser.parse_args()


def main() -> int:
    """主函数，返回 0 成功 / 1 失败。"""
    args = _parse_args()

    # ── 初始化 ──────────────────────────────────────────────
    init_logger()
    logger = logging.getLogger(__name__)

    if args.local:
        _try_load_dotenv()

    logger.info(f"{L.START} GLaDOS Checkin v2.0 启动")

    # ── 加载配置 ────────────────────────────────────────────
    try:
        config = Config()
    except ConfigError as e:
        logger.error(f"{L.ERROR} 配置错误: {e}")
        return 1

    if args.dry_run:
        logger.info(f"{L.INFO} 空跑模式，配置加载成功，退出。")
        logger.info(f"{L.INFO} Cookies: {len(config.cookies_list)} 个")
        logger.info(f"{L.INFO} Domains: {config.domains}")
        logger.info(f"{L.INFO} Exchange: {config.exchange_plan}")
        if config.push_channel:
            logger.info(f"{L.INFO} Push: {config.push_channel}")
        return 0

    # ── 执行签到 ────────────────────────────────────────────
    try:
        checker = Checker(config)
        summary = checker.run()

        logger.info(f"\n{L.END} {'=' * 10} 签到总结 {'=' * 10}")
        logger.info(summary.title)
        for line in summary.format_lines():
            logger.info(line)

    except GladosError as e:
        logger.error(f"{L.ERROR} 签到流程异常: {e}")
        # 构造一个错误 summary 用于推送
        title = f"GLaDOS 签到 ❌ 脚本异常"
        content = str(e)
        send_push(config.push_channel, config.push_token, title, content)
        return 1
    except Exception as e:
        logger.exception(f"{L.ERROR} 未预期的错误: {e}")
        title = f"GLaDOS 签到 ❌ 未知错误"
        content = f"```\n{e}\n```"
        send_push(config.push_channel, config.push_token, title, content)
        return 1

    # ── 推送通知 ────────────────────────────────────────────
    if config.push_channel:
        logger.info(f"{L.PUSH} 发送推送通知...")
        success = send_push(
            config.push_channel,
            config.push_token,
            summary.title,
            summary.push_content,
        )
        if success:
            logger.info(f"{L.SUCCESS} 推送成功")
        else:
            logger.warning(f"{L.WARNING} 推送失败")
    else:
        logger.info(f"{L.INFO} 未配置推送渠道，跳过推送")

    logger.info(f"{L.END} 签到完成")

    # 如果有失败的，返回 1
    return 0 if summary.fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())