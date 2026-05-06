from typing import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

from agent.memory import MemoryManager


class MemoryMiddleware(AgentMiddleware):
    """Middleware that injects memory context (L2 + L3 summary) into the system prompt."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager


    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        memory_context = self.memory_manager.get_memory_context()
        if not memory_context.strip():
            return handler(request)

        addendum = MEMORY_CONTEXT_PROMPT + memory_context
        new_content = list(request.system_message.content_blocks) + [
            {"type": "text", "text": addendum}
        ]
        new_system_message = SystemMessage(content=new_content)
        modified_request = request.override(system_message=new_system_message)
        return handler(modified_request)

# ─── Context injection prompt ───

MEMORY_CONTEXT_PROMPT = """\

## Long-Term Memory Context
Below is a summary of relevant memory from previous sessions. Use this context to maintain continuity, respect user preferences, and apply learned lessons. Do NOT repeat or dump this context back to the user verbatim.

---BEGIN MEMORY CONTEXT---
"""