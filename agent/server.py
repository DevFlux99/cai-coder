import queue
import os
import threading
from collections import defaultdict, deque
from concurrent.futures import  ThreadPoolExecutor, Future

from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware, ToolRetryMiddleware, ModelRetryMiddleware, \
    SummarizationMiddleware, ContextEditingMiddleware, ClearToolUsesEdit
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Checkpointer

from .bus.bus import MessageBus
from .bus.events import OutMessage, InMessage
from .memory import MemoryManager
from .middleware import SkillMiddleware, ConversationSummarizerMiddleware
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

def get_agent(
        checkpointer: Checkpointer = None,
        mcptools: list[BaseTool] = None,
        memory_manager: MemoryManager=None
):
    if checkpointer is None:
        checkpointer = InMemorySaver()
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

    middleware_list = [SkillMiddleware()]
    if memory_manager:
        from agent.memory import MemoryMiddleware
        middleware_list.append(MemoryMiddleware(memory_manager))
        logger.debug("MemoryMiddleware added to agent")

    middleware_list.extend([
        TodoListMiddleware(),
        ToolRetryMiddleware(
            max_retries=3,
            initial_delay=1.0,  # 第一次重试前的初始延迟（以秒为单位）
            backoff_factor=2.0  # 指数退避乘数。每次重试等待 initial_delay * (backoff_factor ** retry_number) 秒。
        ),
        ModelRetryMiddleware(
            max_retries=3,
            initial_delay=1.0,  # 第一次重试前的初始延迟（以秒为单位）
            backoff_factor=2.0  # 指数退避乘数。每次重试等待 initial_delay * (backoff_factor ** retry_number) 秒。
        ),
        SummarizationMiddleware(
            model=_build_llm(),
            trigger=[
                ("tokens", 128000)
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
        ),
        ConversationSummarizerMiddleware()
    ])

    agent = create_agent(
        model=_build_llm(),
        system_prompt=construct_system_prompt(),
        tools=agent_tools,
        middleware=middleware_list,
        checkpointer=checkpointer
    )

    logger.debug("Agent 实例创建成功")
    return agent


class AgentLoop:

    def __init__(
            self,bus: MessageBus,
            session_manager: SessionManager=None,
            checkpoint: Checkpointer = None,
            max_workers: int = 4,
            memory_manager:MemoryManager=None
    ):
        if checkpoint is None:
            checkpoint = InMemorySaver()
        self.bus = bus
        self.session_manager = session_manager
        self.agent = get_agent(checkpointer=checkpoint,memory_manager=memory_manager)
        self._running = False
        self._thread = threading.Thread(target=self.run, daemon=True)
        self.max_workers = max_workers
        self.executor = None

        # Session
        self.chat_futures: dict[str, Future] = {} # Active futures per chat_id
        self.chat_queues: dict[str,deque] = defaultdict(deque) # Pending messages
        self.chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


    def run(self):
        self._running = True

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers,thread_name_prefix = "agent_loop")

        try:
            while self._running:
                try:
                    msg = self.bus.consume_inbound(timeout=5)
                except queue.Empty:
                    continue
                except Exception:
                    logger.exception("Error consuming inbound message")
                    continue
                if msg is None:
                    continue

                self._submit_message(msg)

        finally:
            if self.executor:
                self.executor.shutdown(wait=False)
                logger.info("AgentLoop thread pool has been shut down")

    def _process_message(self, msg: InMessage) -> None:
        chat_id = msg.chat_id
        try:
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

        except Exception as e:
            logger.error(f"Error processing message, chat_id={chat_id}, error={e}")
        finally:
            # Remove the future from active futures
            self.chat_futures.pop(chat_id, None)
            self._process_next_message(chat_id)

    def _process_next_message(self, chat_id: str):

        with self.chat_locks[chat_id]:
            if chat_id in self.chat_futures:
                return

            if not  self.chat_queues[chat_id]:
                return

            msg = self.chat_queues[chat_id].popleft()
            future = self.executor.submit(self._process_message, msg)
            self.chat_futures[chat_id] = future
            logger.debug(f"Submitted processing task: chat_i={chat_id}, remaining in queue:{len(self.chat_queues)}")


    def _submit_message(self, msg:InMessage):
        chat_id = msg.chat_id

        with self.chat_locks[chat_id]:
            if chat_id not in self.chat_futures:
                future = self.executor.submit(self._process_message, msg)
                self.chat_futures[chat_id] = future
                logger.debug(f"Submit processing task: chat_id={chat_id}, execute directly")
            else:
                self.chat_queues[chat_id].append(msg)
                logger.debug(f"Submit processing task: chat_i={chat_id}, queue length:{len(self.chat_queues)}")

    def start(self):
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self.executor:
            self.executor.shutdown(wait=False)
        logger.info("AgentLoop has stopped")