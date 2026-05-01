from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from agent import webapp
from agent.bus.bus import global_message_bus
from agent.bus.events import OutMessage
from agent.heartbeat.heatbeat import HeartbeatService
from agent.integration.manager import ChannelManager
from agent.memory import MemoryManager
from agent.server import AgentLoop, get_agent
from agent.session import SessionManager
from agent.tools.memory_tools import init_memory_tools
from agent.utils.common_util import get_working_dir, init_workspace_templates
from agent.utils.logger import get_logger
from agent.tools.crontool import _service as cron_service

logger = get_logger("main")
working_dir = get_working_dir()
checkpoint = InMemorySaver()
direct_agent = get_agent(checkpointer=checkpoint)

def gateway():

    init_workspace_templates(Path(working_dir))
    session_manager = SessionManager(Path(working_dir))

    memory_manager = MemoryManager(Path(working_dir))
    init_memory_tools(memory_manager)

    bus = global_message_bus
    channel_manager = ChannelManager(bus)
    channel_manager.start_all()


    def _get_heartbeat_target() -> tuple[str,str]:
        sessions = session_manager.list_sessions()
        if not sessions:
            return "cli", "skip"
        # sessions 已按 updated_at 降序排列，取最近活跃的会话
        first = sessions[0]
        channel, chat_id = first.key.split(":", 1)
        return channel, chat_id

    def on_heartbeat_execute(content: str)->str:
        config = {"configurable": {"thread_id": "heart_beat"}}
        response = direct_agent.invoke(
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
        checkpoint.delete_thread("heart_beat")
        return response["messages"][-1].content

    def on_heartbeat_notify(content: str)->str:
        channel, chat_id = _get_heartbeat_target()
        msg = OutMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            metadata={}
        )
        bus.publish_outbound(msg)
        return "done"


    heartbeat = HeartbeatService(
        workspace=Path(working_dir),
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify
    )


    agent_loop = AgentLoop(bus=bus,session_manager=session_manager,checkpoint=checkpoint,memory_manager=memory_manager)
    agent_loop.start()
    heartbeat.start()
    cron_service.start()





def run():
    logger.info("=" * 50)
    logger.info("Cai-Coder 服务启动中...")
    logger.info("=" * 50)

    gateway()

    webapp.start()



if __name__ == "__main__":
    run()