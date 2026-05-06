from langchain_core.tools import tool

from agent.utils.common_util import resolve_path
from agent.utils.logger import get_logger

logger = get_logger("read_file_tool")


@tool
def read_file(file_path: str):
    """Read the contents of a file"""
    logger.debug(f"Reading file: {file_path}")
    try:
        safe_path = resolve_path(file_path)
    except ValueError as exc:
        logger.warning(f"File path resolution failed: {file_path} - {exc}")
        return str(exc)

    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"File read successfully: {safe_path} (length: {len(content)} characters)")
        return content
    except FileNotFoundError:
        logger.error(f"File not found: {safe_path}")
        return f"No such file or directory: '{safe_path}'"
