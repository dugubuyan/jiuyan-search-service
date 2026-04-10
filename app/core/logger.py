"""
统一日志配置
使用方式：from app.core.logger import logger
"""
import logging
import os
import sys

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "")

_fmt = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _setup() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    # 控制台
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(_fmt)
    root.addHandler(sh)

    # 文件（仅当 LOG_DIR 配置时）
    if LOG_DIR:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = logging.FileHandler(os.path.join(LOG_DIR, "search-service.log"), encoding="utf-8")
        fh.setFormatter(_fmt)
        root.addHandler(fh)

    return logging.getLogger("search-service")


logger = _setup()
