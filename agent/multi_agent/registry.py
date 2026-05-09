"""
Agent Registry — defines specialized sub-agents and their capabilities.

Each agent definition includes:
- name: unique identifier
- description: what this agent does (used by dispatcher for routing)
- system_prompt: dedicated system prompt
- tools: list of tool names this agent can use
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    tools: List[str] = field(default_factory=list)
    enabled: bool = True


CODE_REVIEW_PROMPT = """You are a senior code reviewer. Your job is to analyze code changes and provide actionable feedback.

Focus areas:
1. **Correctness** — Logic errors, edge cases, off-by-one errors
2. **Security** — Input validation, injection risks, auth issues
3. **Performance** — Unnecessary allocations, N+1 queries, memory leaks
4. **Maintainability** — Naming, complexity, duplication, missing tests
5. **Best Practices** — Language idioms, design patterns

Output format:
- Use bullet points
- Rate severity: 🔴 Critical / 🟡 Medium / 🟢 Minor
- Always suggest a fix for each issue
- End with a summary: Approve / Request Changes
"""

BUG_FIX_PROMPT = """You are an expert bug-fix engineer. Your job is to diagnose and fix bugs in code.

Workflow:
1. **Reproduce** — Understand the bug from the description and error logs
2. **Root Cause** — Trace the code path to find the exact cause
3. **Fix** — Write the minimal, correct fix
4. **Verify** — Explain why the fix works and what edge cases it covers

Rules:
- Fix the root cause, not the symptom
- Prefer minimal changes over refactoring
- Always explain the reasoning
- If unsure, say so rather than guessing
"""

DEVOPS_PROMPT = """You are a DevOps and infrastructure specialist. You help with deployment, configuration, and system operations.

Capabilities:
- Docker and docker-compose setup
- CI/CD pipeline configuration
- Server monitoring and health checks
- Log analysis and troubleshooting
- Environment configuration management
- Database operations (backup, migration, query optimization)

Rules:
- Always verify commands before suggesting
- Consider security implications
- Prefer idempotent operations
- Document non-obvious operations
"""

GENERAL_PROMPT = """You are a general-purpose coding assistant. You handle tasks that don't fit into specialized categories.

You can:
- Answer coding questions
- Write and explain code
- Help with debugging
- Suggest improvements
"""


def _build_default_agents() -> Dict[str, AgentDefinition]:
    return {
        "code-review": AgentDefinition(
            name="code-review",
            description="Code review, PR analysis, code quality assessment, security audit",
            system_prompt=CODE_REVIEW_PROMPT,
            tools=["read_file", "ls", "bash", "http_request"],
        ),
        "bug-fix": AgentDefinition(
            name="bug-fix",
            description="Bug diagnosis, root cause analysis, bug fixing, error debugging",
            system_prompt=BUG_FIX_PROMPT,
            tools=["read_file", "write_file", "ls", "bash", "http_request"],
        ),
        "devops": AgentDefinition(
            name="devops",
            description="Deployment, Docker, CI/CD, server operations, log analysis, infrastructure",
            system_prompt=DEVOPS_PROMPT,
            tools=["bash", "read_file", "write_file", "ls", "http_request"],
        ),
        "general": AgentDefinition(
            name="general",
            description="General coding questions, explanations, and tasks outside specialized scopes",
            system_prompt=GENERAL_PROMPT,
            tools=["read_file", "write_file", "ls", "bash", "http_request"],
        ),
    }


class AgentRegistry:
    """Registry for managing agent definitions."""

    def __init__(self):
        self._agents: Dict[str, AgentDefinition] = _build_default_agents()

    def register(self, definition: AgentDefinition) -> None:
        self._agents[definition.name] = definition

    def get(self, name: str) -> Optional[AgentDefinition]:
        return self._agents.get(name)

    def list_agents(self) -> List[AgentDefinition]:
        return [a for a in self._agents.values() if a.enabled]

    def get_agent_names(self) -> List[str]:
        return [a.name for a in self.list_agents()]

    def get_agent_descriptions(self) -> str:
        lines = []
        for agent in self.list_agents():
            lines.append(f"- **{agent.name}**: {agent.description}")
        return "\n".join(lines)


agent_registry = AgentRegistry()
