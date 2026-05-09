"""
Delegate Agent Tool — allows the main agent to delegate tasks to specialized agents.

The main agent can explicitly choose an agent by name or let the dispatcher
auto-route based on the task description.
"""

from typing import Any, Dict, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from agent.multi_agent.dispatcher import AgentDispatcher
from agent.multi_agent.registry import agent_registry
from agent.utils.logger import get_logger

logger = get_logger("agent.tools.delegate_agent")


class DelegateAgentInput(BaseModel):
    task: str = Field(description="The task description to delegate to a specialized agent")
    agent_name: Optional[str] = Field(
        default=None,
        description=(
            "Name of the target agent. Options: "
            f"{agent_registry.get_agent_names()}. "
            "If omitted, the dispatcher auto-selects the best agent."
        ),
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="Optional thread ID for conversation continuity with the sub-agent",
    )


class DelegateAgentTool(BaseTool):
    name: str = "delegate_agent"
    description: str = (
        "Delegate a task to a specialized sub-agent. "
        f"Available agents: {agent_registry.get_agent_names()}. "
        "Use this when the task is better handled by a domain expert."
    )
    args_schema: Type[BaseModel] = DelegateAgentInput
    _dispatcher: AgentDispatcher = None

    class Config:
        arbitrary_types_allowed = True

    def set_dispatcher(self, dispatcher: AgentDispatcher) -> None:
        self._dispatcher = dispatcher

    def _run(
        self,
        task: str,
        agent_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._dispatcher is None:
            return {"error": "Dispatcher not initialized"}
        return self._dispatcher.dispatch(task, agent_name, thread_id)

    async def _arun(
        self,
        task: str,
        agent_name: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._run(task, agent_name, thread_id)


delegate_agent_tool = DelegateAgentTool()
