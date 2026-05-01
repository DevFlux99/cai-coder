from langchain_core.tools import tool

from agent.memory import MemoryManager
from agent.utils.logger import get_logger

log = get_logger("memory_tools")

_memory_manager:MemoryManager


def init_memory_tools(manager:MemoryManager) -> None:
    """Set the module-level MemoryManager singleton."""
    global _memory_manager
    _memory_manager = manager


def _get_manager():
    if _memory_manager is None:
        raise RuntimeError("MemoryManager not initialized. Call init_memory_tools first.")
    return _memory_manager


@tool
def save_user_fact(key: str, value: str) -> str:
    """Save a fact about the user to long-term memory profile.
    Use this to remember the user's role, work context, commonly used tools,
    timezone, name, or any personal detail worth persisting.

    Args:
        key: Category/label for the fact (e.g. "role", "timezone", "team").
        value: The fact value.
    """
    mgr = _get_manager()
    mgr.update_profile(key, value)
    return f"Saved user fact: {key} = {value}"


@tool
def save_preference(key: str, value: str) -> str:
    """Save a user preference to long-term memory.
    Use this for language style, output format, naming conventions,
    or things the user has asked you NOT to do.

    Args:
        key: Preference category (e.g. "language_style", "format", "avoid").
        value: The preference value.
    """
    mgr = _get_manager()
    mgr.update_preferences(key, value)
    return f"Saved preference: {key} = {value}"

@tool
def save_glossary_term(term: str, definition: str) -> str:
    """Add or update a term in the glossary.
    Use this to ensure consistent terminology across sessions.

    Args:
        term: The term or abbreviation.
        definition: Its meaning or expansion.
    """
    mgr = _get_manager()
    mgr.update_glossary(term, definition)
    return f"Glossary updated: {term}"



