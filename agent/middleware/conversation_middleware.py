import uuid
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import get_buffer_string
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import StateT
from langgraph.typing import ContextT

from agent.subagents.service import get_memory_agent
from agent.utils.logger import get_logger

log = get_logger("conversation_summarizer")

_SYS_PROMPT = """

    ## Long-Term Memory
    You have access to long-term memory tools. Use them proactively:
    - When the user shares personal details, preferences, or constraints, save them using `save_user_fact` or `save_preference`.
    
    The following dialogue content:
    
"""

class ConversationSummarizerMiddleware(AgentMiddleware):
    def __init__(self):
        self.checkpoint = InMemorySaver()
        self.agent = get_memory_agent(
                sys_prompt="You are an assistant specialized in extracting experience from contextual conversations.",
                checkpointer = self.checkpoint
            )

    def after_agent(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        # 1. 从 state 中获取对话历史
        messages = state.get("messages", [])

        # 2. 仅在对话达到一定长度时总结（避免频繁总结）
        if len(messages) > 5:
            # 3. 调用 LLM 生成摘要
            summary_prompt = _SYS_PROMPT + get_buffer_string(messages)

            thread_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": thread_id}}
            response = self.agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": summary_prompt
                        }
                    ]
                },
                config=config
            )

            self.checkpoint.delete_thread(thread_id)
            log.debug(f"conversation_summarizer: 对话摘要已更新: {response['messages'][-1].content}")

        return None


