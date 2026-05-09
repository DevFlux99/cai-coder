"""
Agent Factory — builds LangGraph agents from AgentDefinition.

Creates specialized agents with their own system prompts and tool sets,
sharing the same LLM instance and checkpointer from the main agent.
"""

import logging
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from agent.multi_agent.registry import AgentDefinition, agent_registry
from agent.utils.logger import get_logger

logger = get_logger("agent.multi_agent.factory")


class AgentFactory:
    """Builds and caches specialized sub-agents."""

    def __init__(
        self,
        llm: BaseChatModel,
        available_tools: Dict[str, BaseTool],
        checkpointer: Any = None,
    ):
        self._llm = llm
        self._available_tools = available_tools
        self._checkpointer = checkpointer
        self._cache: Dict[str, Any] = {}

    def _resolve_tools(self, tool_names: List[str]) -> List[BaseTool]:
        tools = []
        for name in tool_names:
            tool = self._available_tools.get(name)
            if tool is not None:
                tools.append(tool)
            else:
                logger.warning(f"Tool '{name}' not found, skipping")
        return tools

    def build(self, agent_name: str) -> Optional[Any]:
        definition = agent_registry.get(agent_name)
        if definition is None:
            logger.error(f"Agent '{agent_name}' not found in registry")
            return None
        if not definition.enabled:
            logger.warning(f"Agent '{agent_name}' is disabled")
            return None

        tools = self._resolve_tools(definition.tools)
        if not tools:
            logger.warning(
                f"Agent '{agent_name}' has no resolved tools, "
                "falling back to all available tools"
            )
            tools = list(self._available_tools.values())

        compiled_agent = create_react_agent(
            self._llm,
            tools=tools,
            prompt=definition.system_prompt,
        )
        logger.info(
            f"Built agent '{agent_name}' with {len(tools)} tools: "
            f"{[t.name for t in tools]}"
        )
        return compiled_agent

    def get_or_build(self, agent_name: str) -> Optional[Any]:
        if agent_name in self._cache:
            return self._cache[agent_name]
        agent = self.build(agent_name)
        if agent is not None:
            self._cache[agent_name] = agent
        return agent

    def build_all(self) -> Dict[str, Any]:
        agents = {}
        for agent_def in agent_registry.list_agents():
            compiled = self.get_or_build(agent_def.name)
            if compiled is not None:
                agents[agent_def.name] = compiled
        return agents

    def clear_cache(self) -> None:
        self._cache.clear()
