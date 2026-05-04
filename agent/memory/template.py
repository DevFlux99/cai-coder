
# ─── L1 Session log entry template ───

SESSION_LOG_ENTRY = """\

---

### Session {session_id}
- **Time**: {timestamp}
- **Summary**: {summary}
- **Key Decisions**: {decisions}
- **Errors/Issues**: {errors}
"""

# ─── L3 Lesson learned template ───

LESSON_TEMPLATE = """\
# Lesson: {task}
- **Date**: {date}
- **Task**: {task}
- **Mistake**: {mistake}
- **Solution**: {solution}
"""

# ─── L3 Decision record template ───

DECISION_TEMPLATE = """\
# Decision: {topic}
- **Date**: {date}
- **Topic**: {topic}
- **Context**: {context}
- **Decision**: {decision}
- **Rationale**: {rationale}
"""

# ─── L3 Domain knowledge template ───

KNOWLEDGE_TEMPLATE = """\
# Knowledge: {topic}
{content}
"""


# ─── L3 Project background template ───

PROJECT_TEMPLATE = """\
# Project: {name}
> Last Updated: {date}
{background}
"""