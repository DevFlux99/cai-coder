import os

from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer

from agent.middleware import SkillMiddleware

from agent.utils.logger import get_logger

log = get_logger("sub_agent")

def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.7,
    )

def get_sub_agent(sys_prompt:str, checkpointer: Checkpointer = InMemorySaver(), mcptools: list[BaseTool] = None):

    # Deferred import to avoid circular dependencies
    from agent.tools import get_weather, read_file, write_file, ls, bash, http_request, http_get, http_post

    log.debug("正在创建 SubAgent 实例...")

    agent_tools = [
        get_weather,
        read_file,
        write_file,
        ls,
        bash,
        http_request,
        http_get,
        http_post
    ]

    if mcptools:
        log.debug(f"添加 {len(mcptools)} 个 MCP 工具")
        agent_tools.extend(mcptools)

    log.debug(f"SubAgent 工具总数: {len(agent_tools)}")

    agent = create_agent(
        model=_build_llm(),
        system_prompt=sys_prompt,
        tools=agent_tools,
        middleware=[
            SkillMiddleware(),
            TodoListMiddleware(),
        ],
        checkpointer=checkpointer
    )

    log.debug("SubAgent 实例创建成功")
    return agent


def get_memory_agent(sys_prompt:str, checkpointer: Checkpointer = InMemorySaver()):
    from agent.tools import save_user_fact, save_preference, save_glossary_term,append_session_summary

    agent_tools = [
        save_user_fact,
        save_preference,
        save_glossary_term,
        append_session_summary
    ]

    agent = create_agent(
        model=_build_llm(),
        system_prompt=sys_prompt,
        tools=agent_tools,
        checkpointer=checkpointer
    )

    return agent
