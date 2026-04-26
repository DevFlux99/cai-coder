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
    创建并启动一个定时任务，任务执行时将通过指定渠道将消息推送到当前会话中。

    Args:
        kind (Literal["at", "every"]): 定时任务的触发类型。
            - "at": 在某个绝对时间点触发一次。
            - "every": 按固定周期循环触发。
            - "cron": 使用cron表达式触发
        time_ms (int): 时间配置，单位严格为毫秒。
            - 当 kind 为 "at" 时：必须是未来的**绝对时间戳**（如 Unix 毫秒级时间戳 1690000000000）。禁止传入相对时间！
            - 当 kind 为 "every" 时：表示执行的间隔时长（如 5000 代表每 5 秒执行一次）。
            - 当 kind 为 "cron" 时：填 0
        expr (str): cron表达式符号
            - 当 kind 为 "cron" 时：标准的 Cron 表达式符号, 分别代表：分钟、小时、日期、月份、星期），中间用空格隔开
            - 当 kind 不为 "cron" 时：填none
        name (str): 定时任务的唯一名称标识，用于后续管理、查询或取消任务。
        message (str): 定时任务触发时需要发送的具体消息内容。
            - 当 event 为 "system_event" 时：请直接填入用户希望发送的完整文本。
            - 当 event 为 "agent_turn" 时：把事情描述给Agent, Agent会自动执行。
        channel (Literal["feishu", "cli"]): 任务触发后的消息推送渠道。
            - "feishu": 推送到飞书，默认推送渠道为feishu。
            - "cli": 推送到本地命令行终端，除非用户说推送到终端，否则不走这个channel。
        event (Literal["system_event", "agent_turn"]): 消息的处理与发送方式。
            - "system_event": 将 message 作为纯文本直接推送到渠道。
            - "agent_turn": 将 message 作为工作内容交由 Agent 处理，然后将 Agent 的回复内容推送到渠道。

    Returns:
        CronJob: 成功创建的定时任务对象，包含任务状态等详细信息。
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

