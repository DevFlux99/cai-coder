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
    log.debug(f"Saved user fact: {key} = {value}")
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
    log.debug(f"Saved preference: {key} = {value}")
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


@tool
def append_session_summary(
    session_id: str,
    summary: str,
    decisions: list[str],
    errors: list[str],
) -> str:
    """Append a summary of the current session to the daily log.
    Call this at the end of a significant session or when the user
    explicitly asks you to remember the conversation.

    Args:
        session_id: Unique session identifier.
        summary: Brief summary of the conversation.
        decisions: Key decisions made during the session.
        errors: Errors or issues encountered.
    """
    mgr = _get_manager()
    path = mgr.append_session_log(session_id, summary, decisions, errors)
    log.debug(f"Session summary appended to: {path}")
    return f"Session summary appended to: {path}"


@tool
def save_lesson_learned(task: str, mistake: str, solution: str) -> str:
    """Record a lesson learned from an error or pitfall encountered and resolved.
    Call this after debugging a tricky issue, recovering from a mistake, or
    discovering a non-obvious solution.

    Args:
        task: What you were trying to do.
        mistake: What went wrong or what the pitfall was.
        solution: How it was resolved or what should be done differently.
    """
    mgr = _get_manager()
    path = mgr.add_lesson(task, mistake, solution)
    log.debug(f"Lesson recorded at: {path}")
    return f"Lesson recorded at: {path}"

@tool
def save_decision(topic: str, context: str, decision: str, rationale: str) -> str:
    """Record a significant architectural or design decision.
    Use this when you or the user make an important technical choice
    that future sessions should be aware of.

    Args:
        topic: Short topic name (e.g. "database-choice", "api-design").
        context: The situation or constraints driving the decision.
        decision: What was decided.
        rationale: Why this decision was made.
    """
    mgr = _get_manager()
    path = mgr.add_decision(topic, context, decision, rationale)
    log.debug(f"Decision recorded at: {path}")
    return f"Decision recorded at: {path}"


@tool
def save_project_background(name: str, background: str) -> str:
    """Save or update background information about a project.
    Use this when starting work on a new project or when significant
    project context is established.

    Args:
        name: Project identifier (e.g. "cai-coder", "data-pipeline").
        background: Project description, constraints, tech stack, goals.
    """
    mgr = _get_manager()
    path = mgr.add_project(name, background)
    log.debug(f"Project background saved at: {path}")
    return f"Project background saved at: {path}"

@tool
def save_knowledge(topic: str, content: str) -> str:
    """Save domain knowledge or reference material for future use.
    Use this for technical guides, how-tos, or domain-specific information
    that may be useful across multiple sessions.

    Args:
        topic: Knowledge topic (e.g. "kafka-setup", "react-patterns").
        content: The knowledge content in markdown format.
    """
    mgr = _get_manager()
    path = mgr.add_knowledge(topic, content)
    log.debug(f"Knowledge saved at: {path}")
    return f"Knowledge saved at: {path}"

@tool
def save_journal_entry(content: str) -> str:
    """Append an entry to today's journal in long-term memory.
    Use this to record notable events, achievements, or reflections
    from the current session.

    Args:
        content: Journal entry content.
    """
    mgr = _get_manager()
    path = mgr.add_journal_entry(content)
    log.debug(f"Journal entry saved at: {path}")
    return f"Journal entry saved at: {path}"