"""日志配置：北京时间格式化，统一获取 logger。"""

from __future__ import annotations

import datetime
import logging
import logging.config
import sys
import time
from typing import Any


def _beijing_time_converter(timestamp: float) -> time.struct_time:
    """将 UTC 时间戳转换为北京时间 struct_time。"""
    utc_dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    beijing_dt = utc_dt.astimezone(beijing_tz)
    return beijing_dt.timetuple()


LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s | %(levelname)-8s | %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "converter": _beijing_time_converter,
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


def init_logger(name: str | None = None) -> logging.Logger:
    """初始化日志配置并返回 Logger 实例。"""
    logging.config.dictConfig(LOGGING_CONFIG)
    return logging.getLogger(name)