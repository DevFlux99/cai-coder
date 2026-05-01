
# ─── L1 会话日志条目模板 ───

SESSION_LOG_ENTRY = """\

---

### Session {session_id}
- **Time**: {timestamp}
- **Summary**: {summary}
- **Key Decisions**: {decisions}
- **Errors/Issues**: {errors}
"""

# ─── L3 经验教训模板 ───

LESSON_TEMPLATE = """\
# Lesson: {task}
- **Date**: {date}
- **Task**: {task}
- **Mistake**: {mistake}
- **Solution**: {solution}
"""

# ─── L3 决策记录模板 ───

DECISION_TEMPLATE = """\
# Decision: {topic}
- **Date**: {date}
- **Topic**: {topic}
- **Context**: {context}
- **Decision**: {decision}
- **Rationale**: {rationale}
"""

# ─── L3 领域知识模板 ───

KNOWLEDGE_TEMPLATE = """\
# Knowledge: {topic}
{content}
"""


# ─── L3 项目背景模板 ───

PROJECT_TEMPLATE = """\
# Project: {name}
> Last Updated: {date}
{background}
"""