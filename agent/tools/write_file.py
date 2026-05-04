import os

from langchain_core.tools import tool

from agent.utils.common_util import resolve_path
from agent.utils.logger import get_logger

logger = get_logger("write_file_tool")


@tool
def write_file(file_path: str, content: str):
    """Write contents to a file"""
    logger.debug(f"Writing file: {file_path} (length: {len(content)} characters)")
    try:
        safe_path = resolve_path(file_path)
    except ValueError as exc:
        logger.warning(f"File path resolution failed: {file_path} - {exc}")
        return {"success": False, "error": str(exc)}

    parent = os.path.dirname(safe_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(safe_path, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info(f"File written successfully: {safe_path}")
    return {"success": True}