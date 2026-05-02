import queue
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import get_buffer_string, BaseMessage
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
    _MAX_RECORD_SIZE = 1000

    def __init__(self, max_workers: int = 2, max_queue: int = 50):
        self._pending = queue.Queue(maxsize=max_queue)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._start_workers(max_workers)
        self._record_messages_ids:dict[str, str|None] = {}

    def _start_workers(self, workers: int):
        for _ in range(workers):
            self._executor.submit(self._worker)

    def _worker(self):
        while True:
            summary_prompt = self._pending.get()
            try:
                self._run_summary(summary_prompt)
            except Exception:
                log.exception("conversation_summarizer: worker 异常")
            self._pending.task_done()

    def _run_summary(self, summary_prompt: str):
        checkpointer = InMemorySaver()
        agent = get_memory_agent(
            sys_prompt="You are an assistant specialized in extracting experience from contextual conversations.",
            checkpointer=checkpointer,
        )
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": summary_prompt}]},
                config=config,
            )
            checkpointer.delete_thread(thread_id)
            log.debug(f"conversation_summarizer: 对话摘要已更新: {response['messages'][-1].content}")
        except Exception:
            log.exception("conversation_summarizer: 后台总结任务失败")

    def after_agent(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        messages: list[BaseMessage]= state.get("messages", [])
        thread_id = runtime.execution_info.thread_id
        last_messages_id = self._record_messages_ids.get(thread_id)

        start_index = 0
        if last_messages_id:
            for i, msg in enumerate(messages):
                if msg.id == last_messages_id:
                    start_index = i + 1
                    break

        # 截取从该标记之后的所有消息（包含压缩后遗留的）
        current_turn_messages = messages[start_index:]
        if len(current_turn_messages) > 20:
            summary_prompt = _SYS_PROMPT + get_buffer_string(current_turn_messages)
            self._record_messages_ids[thread_id] = state["messages"][-1].id if state["messages"] else None
            if len(self._record_messages_ids) > self._MAX_RECORD_SIZE:
                oldest_keys = list(self._record_messages_ids.keys())[:len(self._record_messages_ids) - self._MAX_RECORD_SIZE // 2]
                for k in oldest_keys:
                    del self._record_messages_ids[k]
            try:
                self._pending.put_nowait(summary_prompt)
            except queue.Full:
                log.warning("conversation_summarizer: 队列已满，丢弃本次总结任务")

        return None