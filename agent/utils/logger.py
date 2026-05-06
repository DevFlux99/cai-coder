import os

from loguru import logger
import sys
from typing import Optional

# Configure loguru
def setup_logger(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    format_string: Optional[str] = None
):
    """
    Configure loguru logger.

    Args:
        level: Log level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        log_file: Optional log file path
        rotation: Log rotation size (e.g. "10 MB")
        retention: Log retention period (e.g. "7 days")
        format_string: Optional custom format string
    """
    if format_string is None:
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

    # Remove default handler
    logger.remove()

    # Console handler
    logger.add(
        sys.stdout,
        format=format_string,
        level=level,
        colorize=True
    )

    # File handler (optional)
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

# Default configuration
setup_logger(
    level=os.getenv("LOG_LEVEL") or "INFO"
)

def get_logger(name: str = "cai-coder"):
    """
    Get a logger instance.

    Args:
        name: Logger name

    Returns:
        loguru logger instance
    """
    return logger.bind(name=name)
