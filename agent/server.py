import os
import threading

from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware, ToolRetryMiddleware, ModelRetryMiddleware, \
    SummarizationMiddleware, ContextEditingMiddleware, ClearToolUsesEdit
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer

from .bus.bus import MessageBus
from .bus.events import OutMessage
from .middleware import SkillMiddleware
from .session import SessionManager
from .tools import (
    get_weather,
    read_file,
    write_file,
    ls,
    bash,
    http_request,
    http_get,
    http_post, add_cronjob, send_im_messages
)
from .prompt import construct_system_prompt
from .utils.logger import get_logger

logger = get_logger("server")

_REQUIRED_ENV_VARS = ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL")


def _check_env_vars() -> None:
    missing = [var for var in _REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        logger.error(f"缺少必需的环境变量: {', '.join(missing)}")
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Please set them in .local.env or your shell environment."
        )
    logger.debug("环境变量检查通过")


def _build_llm() -> ChatOpenAI:
    _check_env_vars()
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.7,
    )

def get_agent(checkpointer: Checkpointer = InMemorySaver(), mcptools: list[BaseTool] = None):
    logger.debug("正在创建 Agent 实例...")

    agent_tools = [
        get_weather,
        read_file,
        write_file,
        ls,
        bash,
        http_request,
        http_get,
        http_post,
        add_cronjob,
        send_im_messages
    ]

    if mcptools:
        logger.debug(f"添加 {len(mcptools)} 个 MCP 工具")
        agent_tools.extend(mcptools)

    logger.debug(f"Agent 工具总数: {len(agent_tools)}")

    agent = create_agent(
        model=_build_llm(),
        system_prompt=construct_system_prompt(),
        tools=agent_tools,
        middleware=[
            SkillMiddleware(),
            TodoListMiddleware(),
            ToolRetryMiddleware(
                max_retries=3,
                initial_delay=1.0,  # 第一次重试前的初始延迟（以秒为单位）
                backoff_factor=2.0 # 指数退避乘数。每次重试等待 initial_delay * (backoff_factor ** retry_number) 秒。
            ),
            ModelRetryMiddleware(
                max_retries=3,
                initial_delay=1.0,  # 第一次重试前的初始延迟（以秒为单位）
                backoff_factor=2.0  # 指数退避乘数。每次重试等待 initial_delay * (backoff_factor ** retry_number) 秒。
            ),
            SummarizationMiddleware(
                model=_build_llm(),
                trigger= [
                    ("tokens",128000)
                ],
                keep=("tokens", 80000)
            ),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=64000,
                        keep=5,
                        clear_tool_inputs=False,
                        exclude_tools=[],
                        placeholder="[cleared]",
                    )
                ]
            )
        ],
        checkpointer=checkpointer
    )

    logger.debug("Agent 实例创建成功")
    return agent


class AgentLoop:

    def __init__(
            self,bus: MessageBus,
            session_manager: SessionManager=None,
            checkpoint: Checkpointer = InMemorySaver()):
        self.bus = bus
        self.session_manager = session_manager
        self.agent = get_agent(checkpointer=checkpoint)
        self._running = False
        self._thread = threading.Thread(target=self.run, daemon=True)


    def run(self):
        self._running = True
        while self._running:
            try:
                msg = self.bus.consume_inbound(timeout=5)
            except Exception:
                continue
            if msg is None:
                continue
            content = msg.content
            chat_id = msg.chat_id
            channel = msg.channel

            if self.session_manager:
                self.session_manager.get_or_create(f"{channel}:{chat_id}")

            config = {"configurable": {"thread_id": chat_id}}
            response = self.agent.invoke({"messages": [{"role": "user", "content": content}]}, config=config)
            out_message = OutMessage(
                channel=channel,
                chat_id=chat_id,
                content="[AGENT_FINISHED]",
                metadata=msg.metadata
            )
            self.bus.publish_outbound(out_message)


    def start(self):
        self._thread.start()

    def stop(self):
        self._running = False