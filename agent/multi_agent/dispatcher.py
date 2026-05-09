"""
Agent Dispatcher — routes tasks to the most appropriate specialized agent.

Uses LLM-based classification to determine which agent should handle a task,
then delegates execution and returns the result.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from agent.multi_agent.factory import AgentFactory
from agent.multi_agent.registry import agent_registry
from agent.utils.logger import get_logger

logger = get_logger("agent.multi_agent.dispatcher")

ROUTING_PROMPT = """You are a task router. Given a user's task, determine which specialized agent should handle it.

Available agents:
{agent_descriptions}

Respond with ONLY the agent name (e.g., "code-review"), nothing else.
If unsure, respond with "general".
"""


class AgentDispatcher:
    """Routes user tasks to specialized agents."""

    def __init__(self, factory: AgentFactory, llm: BaseChatModel):
        self._factory = factory
        self._llm = llm
        self._routing_prompt = ROUTING_PROMPT.format(
            agent_descriptions=agent_registry.get_agent_descriptions()
        )

    def classify_task(self, task: str) -> str:
        message = HumanMessage(
            content=f"{self._routing_prompt}\n\nTask: {task}"
        )
        response = self._llm.invoke([message])
        agent_name = response.content.strip().lower()

        valid_names = agent_registry.get_agent_names()
        if agent_name not in valid_names:
            logger.warning(
                f"LLM returned unknown agent '{agent_name}', "
                f"falling back to 'general'"
            )
            return "general"

        logger.info(f"Task classified → agent: {agent_name}")
        return agent_name

    def dispatch(
        self,
        task: str,
        agent_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if agent_name is None:
            agent_name = self.classify_task(task)

        agent_def = agent_registry.get(agent_name)
        if agent_def is None:
            return {
                "error": f"Agent '{agent_name}' not found",
                "available": agent_registry.get_agent_names(),
            }

        compiled = self._factory.get_or_build(agent_name)
        if compiled is None:
            return {"error": f"Failed to build agent '{agent_name}'"}

        config = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}

        try:
            result = compiled.invoke(
                {"messages": [HumanMessage(content=task)]},
                config=config if config else None,
            )
            messages = result.get("messages", [])
            final_response = ""
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.type != "human":
                    final_response = msg.content
                    break

            logger.info(
                f"Agent '{agent_name}' completed task "
                f"({len(messages)} messages)"
            )
            return {
                "agent": agent_name,
                "response": final_response,
                "message_count": len(messages),
            }
        except Exception as e:
            logger.error(f"Agent '{agent_name}' failed: {e}")
            return {
                "agent": agent_name,
                "error": str(e),
            }
