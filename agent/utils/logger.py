import os

from loguru import logger
import sys
from typing import Optional

# 配置 loguru
def setup_logger(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    format_string: Optional[str] = None
):
    """
    配置 loguru 日志记录器。

    Args:
        level: 日志级别 ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        log_file: 可选的日志文件路径
        rotation: 日志轮转大小 (如 "10 MB")
        retention: 日志保留时间 (如 "7 days")
        format_string: 可选的自定义格式字符串
    """
    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    # 移除默认的处理器
    logger.remove()

    # 控制台处理器
    logger.add(
        sys.stdout,
        format=format_string,
        level=level,
        colorize=True
    )

    # 文件处理器（可选）
    if log_file:
        logger.add(
            log_file,
            format=format_string,
            level=level,
            rotation=rotation,
            retention=retention,
            compression="zip"
        )

    return logger

# 默认配置
setup_logger(
    level=os.getenv("LOG_LEVEL") or "INFO"
)

def get_logger(name: str = "cai-coder"):
    """
    获取一个日志记录器。

    Args:
        name: 日志记录器名称

    Returns:
        loguru logger 实例
    """
    return logger.bind(name=name)
