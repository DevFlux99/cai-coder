from typing import Literal

from langchain_core.tools import tool

from agent.bus.bus import global_message_bus
from agent.bus.events import OutMessage


@tool
def send_im_messages(
        channel: Literal["feishu"],
        chat_id: str,
        content: str,
        message_id: str,
        media: list[str],
):
    """Send a message to a target session via a specified IM channel.

        This tool publishes the message to the internal message bus, and the corresponding channel service (such as the Feishu bot) completes the actual message delivery.
        Note: This is only used for sending new messages and does not support replying to a specific message.

        Args:
            channel (str): The name of the IM channel. For example: "feishu" (Feishu), "dingtalk" (DingTalk, currently not supported), "wechat" (WeCom, currently not supported), etc.
            chat_id (str): The unique identification ID of the target session or group chat. Usually obtained from the context of the user's incoming message.
            content (str): The specific message text content to be sent (plain text or Markdown supported by specific formats).
            message_id (str): The ID of the associated source message. Usually used for message link tracing or recording "which user message this is a reply to".
            media (list[str]): A list of absolute paths to local files or images to be sent along with the message. For example: ["/data/uploads/img.png", "/data/docs/report.pdf"]. If there are no attachments, an empty list [] must be passed; strictly do not pass None.
        Returns:
            str: Returns a confirmation message of the sending result, for example: "消息发送成功".
        """
    out_message = OutMessage(
        channel=channel,
        chat_id=chat_id,
        content=content,
        metadata={
            "message_id": message_id,
            "media": media
        }
    )
    global_message_bus.publish_outbound(out_message)