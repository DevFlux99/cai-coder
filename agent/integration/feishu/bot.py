import datetime
import json
import queue
import random
from collections import OrderedDict
from typing import Dict

from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, ReplyMessageRequest, \
    ReplyMessageRequestBody, CreateMessageReactionRequest, CreateMessageReactionRequestBuilder, EmojiBuilder, \
    CreateMessageReactionRequestBody, Emoji, DeleteMessageReactionRequest

from agent.bus.bus import MessageBus
from agent.bus.events import OutMessage
from agent.integration.base import BaseChannel
from agent.integration.feishu.config import FeishuBotConfig
from agent.utils.logger import get_logger
import lark_oapi as lark

logger = get_logger("feishu_bot")

class FeishuChannel(BaseChannel):
    name = "feishu"

    def __init__(self, bus: MessageBus):
        super().__init__(bus)

        # 初始化日志记录器
        self.logger = get_logger("feishu_bot")

        # 同步阻塞队列， 处理100条消息
        self.task_queue = queue.Queue(maxsize=100)

        # 验证配置
        FeishuBotConfig.validate()

        self.task_db: OrderedDict[str, None] = OrderedDict()
        self._task_db_max_size = 10000

        # 会话过期时间
        self.session_timeout = FeishuBotConfig.SESSION_TIMEOUT

        # 会话最后活跃时间记录
        self.session_last_active: Dict[str, datetime] = {}

        # 创建事件处理器
        self.event_handler = self._create_event_handler()

        # 创建长连接客户端
        self.client = lark.ws.Client(
            FeishuBotConfig.FEISHU_APP_ID,
            FeishuBotConfig.FEISHU_APP_SECRET,
            event_handler=self.event_handler,
            log_level=lark.LogLevel.DEBUG
        )

        self.client2 = lark.Client.builder() \
            .app_id(FeishuBotConfig.FEISHU_APP_ID,) \
            .app_secret(FeishuBotConfig.FEISHU_APP_SECRET) \
            .log_level(lark.LogLevel.DEBUG) \
            .build()

    def _create_event_handler(self):
        """创建事件处理器"""
        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_receive)
            .build()
        )

    def send(self, msg: OutMessage) -> None:
        chat_id = msg.chat_id
        content = msg.content
        metadata = msg.metadata

        # 如果metadata 没有额外的消息，则主动发消息
        if metadata == {}:
            self._send_message(chat_id=chat_id,text=content)
            return

        message_id = metadata.get("message_id")
        reaction_id = metadata.get("reaction_id")
        # 删除表情
        if reaction_id:
            self._reply_message_reaction_delete(message_id=message_id, reaction_id=reaction_id)
        if content == "[AGENT_FINISHED]":
            return
        self._reply_message(message_id, content)
        self.logger.info(f"[发送回复] message_id={message_id}, reply={content[:100]}...")

    def _handle_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """
        处理接收消息事件

        Args:
            data: 飞书消息事件数据
        """
        try:
            # 提取消息信息
            event = data.event
            message = event.message
            content = message.content
            chat_id = message.chat_id
            message_id = message.message_id
            sender = event.sender

            # 解析消息内容（飞书消息是 JSON 格式）
            content_dict = json.loads(content)
            text = content_dict.get("text", "")

            if not text:
                return

            # 消息已经回复过，直接跳过，避免长链接重放
            if message_id in self.task_db:
                self.logger.info(f"[消息重复] message_id={message_id} 已经跳过")
                return

            final_text = text
            # 获取 mentions 数组（如果没有@任何人，这个字段可能为空）
            mentions = event.message.mentions

            if mentions:
                for mention in mentions:
                    key = mention.key
                    name = mention.name

                    final_text = final_text.replace(key, f"@{name}")


            self.logger.info(
                f"[收到消息] chat_id={chat_id}, message_id={message_id}, "
                f"sender={sender.sender_id.user_id}, text={final_text}"
            )

            # 表情回复
            reaction_id = self._reply_message_reaction_create(message_id=message_id)

            metadata = {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction_id": reaction_id,
            }

            content = ("=== Conversation info (trusted metadata) ===\n"
                       + json.dumps(metadata, ensure_ascii=False, indent=2) + "\n\n"  +final_text)


            logger.debug("handle messages: " + content)

            self._handle_message(
                chat_id=chat_id,
                content=content,
                metadata=metadata
            )

            self.task_db[message_id] = None
            if len(self.task_db) > self._task_db_max_size:
                self.task_db.popitem(last=False)

        except Exception as e:
            self.logger.error(f"处理消息时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())


    def _reply_message_reaction_create(self, message_id: str) -> str:
        emojis = ["MeMeMe","Typing","OneSecond","SLIGHT","ClownFace","SHOCKED","HUG","EMBARRASSED","SMIRK","WOW","KISS"]
        emoji_type = random.choice(emojis)
        request = (
            CreateMessageReactionRequest.builder()
            .message_id(message_id)
            .request_body(
                CreateMessageReactionRequestBody.builder()
                .reaction_type(
                    Emoji.builder().emoji_type(emoji_type).build()
                ).build()
            )
            .build()
        )

        response = self.client2.im.v1.message_reaction.create(request)

        if not response.success():
            self.logger.error(f"添加表情失败: code={response.code}, msg={response.msg}")
            return ""
        else:
            self.logger.debug("添加表情成功")
            return response.data.reaction_id

    def _reply_message_reaction_delete(self, message_id: str, reaction_id: str):
        request = (
            DeleteMessageReactionRequest.builder()
            .message_id(message_id)
            .reaction_id(reaction_id)
            .build()
        )

        response = self.client2.im.v1.message_reaction.delete(request)

        if not response.success():
            self.logger.error(f"删除表情失败: code={response.code}, msg={response.msg}")
        else:
            self.logger.debug("删除表情成功")


    def _reply_message(self, message_id: str, text: str):
        """
        发送消息到飞书

        Args:
            chat_id: 聊天 ID
            text: 消息文本
        """
        reply = {
            "zh_cn": {
                "content": [
                    [{
                        "tag": "md",
                        "text": text
                    }]
                ]
            }
        }


        content = json.dumps(reply, ensure_ascii=False, indent=2)
        try:
            request = ReplyMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(ReplyMessageRequestBody.builder()
                              .msg_type("post") # 指定消息类型为文本
                              .content(content)  # 填入 JSON 字符串
                              .build()) \
                .build()

            response = self.client2.im.v1.message.reply(request)

            if not response.success():
                raise Exception(
                    f"client.im.v1.message.reply failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")

        except Exception as e:
            self.logger.error(f"回复消息时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _send_message(self, chat_id: str, text: str):
        """
        发送消息到飞书

        Args:
            chat_id: 聊天 ID
            text: 消息文本
        """
        reply = {
            "zh_cn": {
                "content": [
                    [{
                        "tag": "md",
                        "text": text
                    }]
                ]
            }
        }
        content = json.dumps(reply, ensure_ascii=False, indent=2)
        try:
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                              .receive_id(chat_id)
                              .msg_type("post")
                              .content(content)
                              .build()) \
                .build()

            response = self.client2.im.v1.message.create(request)

            if not response.success():
                raise Exception(
                    f"client.im.v1.chat.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")

        except Exception as e:
            self.logger.error(f"创建消息时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def start(self) -> None:
        """启动机器人"""
        self.logger.info("=" * 50)
        self.logger.info("飞书长连接机器人启动中...")
        self.logger.info(f"APP_ID: {FeishuBotConfig.FEISHU_APP_ID}")
        self.logger.info(f"会话超时时间: {self.session_timeout} 秒")
        self.logger.info("=" * 50)

        try:
            self.client.start()
        except KeyboardInterrupt:
            self.logger.info("机器人已停止")
        except Exception as e:
            self.logger.error(f"机器人运行出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())