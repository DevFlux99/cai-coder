from typing import Literal

from langchain_core.tools import tool

from agent.bus.bus import global_message_bus
from agent.bus.events import OutMessage


@tool
def send_im_messages(
        channel: Literal["feishu"],
        chat_id: str,
        content: str,
        message_id: str
):
    """通过指定的IM渠道向目标会话发送消息。

    该工具会将消息发布到内部消息总线，由对应的渠道服务（如飞书机器人）完成实际的消息下发。
    注意：仅用于发送新消息，不支持回复特定消息。

    Args:
        channel (str): IM渠道名称。例如："feishu"（飞书）、"dingtalk"（钉钉,目前不支持）、"wechat"（企业微信，目前不支持）等。
        chat_id (str): 目标会话或群聊的唯一标识ID。通常由用户的上行消息上下文中获取。
        content (str): 需要发送的具体消息文本内容（纯文本或特定格式支持的Markdown）。
        message_id (str): 关联的源消息ID。通常用于消息链路追踪或记录“是针对哪条用户消息的回复”。

    Returns:
        str: 返回发送结果的确认信息，例如："消息发送成功"。
    """
    out_message = OutMessage(
        channel=channel,
        chat_id=chat_id,
        content=content,
        metadata={"message_id": message_id}
    )
    global_message_bus.publish_outbound(out_message)