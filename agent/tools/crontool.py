import uuid
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolRuntime

from agent.bus.bus import global_message_bus
from agent.bus.events import OutMessage
from agent.cron import CronService, CronJob, CronSchedule

from langchain_core.tools import tool

from agent.subagents import get_sub_agent
from agent.utils.common_util import get_working_dir
from agent.utils.logger import get_logger

log = get_logger("cron_tool")

_checkpoint = InMemorySaver()

_cronjob_agent = get_sub_agent(
    sys_prompt="You are a sub-agent for a scheduled task, and you will be scheduled to work.",
    checkpointer=_checkpoint
)


def _handle_message(content: str) -> str:
    uid: str = str(uuid.uuid4())
    config = {"configurable": {"thread_id": uid}}
    response = _cronjob_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        },
        config=config
    )
    _checkpoint.delete_thread(uid)
    return response["messages"][-1].content

def push_message(job:CronJob):
    payload = job.payload
    channel = payload["channel"]
    chat_id = payload["chat_id"]
    message = payload["message"]
    event = payload["event"]

    if event == "system_event":
        content = message
    else:
        log.info("The cronjob agent is processing the task")
        content = _handle_message(message)

    out_message = OutMessage(
        channel=channel,
        chat_id=chat_id,
        content=content,
        metadata={}
    )
    global_message_bus.publish_outbound(out_message)

_service = CronService(on_job=push_message,workspace=Path(get_working_dir()))

@tool
def add_cronjob(
        kind: Literal["at", "every","cron"],
        time_ms: int,
        expr: str,
        name: str,
        message: str,
        channel: Literal["feishu", "cli"],
        event: Literal["system_event", "agent_turn"],
        runtime: ToolRuntime
) -> CronJob:
    """
    Create and start a scheduled task. When triggered, the task will push a message to the current conversation via the specified channel.

    Args:
        kind (Literal["at", "every"]): Trigger type of the scheduled task.
            - "at": Trigger once at an absolute time point.
            - "every": Trigger repeatedly at a fixed interval.
            - "cron": Trigger using a cron expression.
        time_ms (int): Time configuration in milliseconds.
            - When kind is "at": Must be a future **absolute timestamp** (e.g. Unix millisecond timestamp 1690000000000). Relative times are NOT allowed!
            - When kind is "every": Represents the execution interval (e.g. 5000 means every 5 seconds).
            - When kind is "cron": Set to 0.
        expr (str): Cron expression.
            - When kind is "cron": Standard cron expression (minute, hour, day of month, month, day of week), separated by spaces.
            - When kind is not "cron": Set to none.
        name (str): Unique name identifier for the scheduled task, used for management, querying, or cancellation.
        message (str): The specific message content to send when the task triggers.
            - When event is "system_event": Fill in the complete text the user wants to send.
            - When event is "agent_turn": Describe the task to the Agent, and the Agent will execute it automatically.
        channel (Literal["feishu", "cli"]): Message push channel after the task triggers.
            - "feishu": Push to Feishu. Default push channel is feishu.
            - "cli": Push to the local command line terminal. Only use this channel if the user explicitly requests terminal output.
        event (Literal["system_event", "agent_turn"]): Message processing and sending method.
            - "system_event": Push message as plain text directly to the channel.
            - "agent_turn": Pass message as work content to the Agent for processing, then push the Agent's reply to the channel.

    Returns:
        CronJob: The successfully created scheduled task object, including task status and other details.
    """
    if kind == "at":
        sched = CronSchedule(
            kind="at",
            at_ms=time_ms
        )
    elif kind == "every":
        sched = CronSchedule(
            kind="every",
            every_ms=time_ms
        )
    else:
        sched = CronSchedule(
            kind="cron",
            expr=expr
        )

    configurable = runtime.config.get("configurable") if runtime.config else {}
    chat_id = configurable.get("thread_id")

    payload = {
        "chat_id": chat_id,
        "channel": channel,
        "message": message,
        "event": event
    }
    added = _service.add_job(name, schedule=sched, payload=payload)

    log.debug(f"add cron job: {name} message:{message}")

    return added

