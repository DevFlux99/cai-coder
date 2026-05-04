import datetime
import json
import os
import queue
import random
from collections import OrderedDict
from typing import Dict

from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, ReplyMessageRequest, \
    ReplyMessageRequestBody, CreateMessageReactionRequest, CreateMessageReactionRequestBuilder, EmojiBuilder, \
    CreateMessageReactionRequestBody, Emoji, DeleteMessageReactionRequest, CreateImageResponse

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

        # Initialize logger
        self.logger = get_logger("feishu_bot")

        # Synchronous blocking queue, handles up to 100 messages
        self.task_queue = queue.Queue(maxsize=100)

        # Validate configuration
        FeishuBotConfig.validate()

        self.task_db: OrderedDict[str, None] = OrderedDict()
        self._task_db_max_size = 10000

        # Session timeout
        self.session_timeout = FeishuBotConfig.SESSION_TIMEOUT

        # Session last active time records
        self.session_last_active: Dict[str, datetime] = {}

        # Create event handler
        self.event_handler = self._create_event_handler()

        # Create long connection client
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
        """Create event handler"""
        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message_receive)
            .build()
        )

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}
    _FILE_TYPE_MAP = {
        ".opus": "opus",
        ".mp4": "mp4",
        ".pdf": "pdf",
        ".doc": "doc",
        ".docx": "doc",
        ".xls": "xls",
        ".xlsx": "xls",
        ".ppt": "ppt",
        ".pptx": "ppt",
    }

    def send(self, msg: OutMessage) -> None:
        chat_id = msg.chat_id
        content = msg.content
        metadata = msg.metadata

        # If metadata has no extra messages, send message proactively
        if metadata == {}:
            self._send_message(chat_id=chat_id,text=content)
            return

        message_id = metadata.get("message_id")
        reaction_id = metadata.get("reaction_id")
        # Delete reaction
        if reaction_id:
            self._reply_message_reaction_delete(message_id=message_id, reaction_id=reaction_id)
        if content == "[AGENT_FINISHED]":
            return

        def _do_reply(msg_type:str, reply_message: str) -> None:
            self._reply_message(message_id, msg_type, reply_message)

        media = metadata.get("media") or []
        for file_path in media:
            if not os.path.isfile(file_path):
                logger.warning("Media file not found: {}", file_path)
                continue
            ext = os.path.splitext(file_path)[1].lower()
            if ext in self._IMAGE_EXTS:
                key = self._upload_image(file_path)
                if key:
                    _do_reply("image", reply_message= json.dumps({"image_key": key}, ensure_ascii=False))

            else:
                key = self._upload_file(file_path)
                if key:
                    _do_reply("file", reply_message= json.dumps({"file_key": key}, ensure_ascii=False))

        if content:
            reply = {
                "zh_cn": {
                    "content": [
                        [{
                            "tag": "md",
                            "text": content
                        }]
                    ]
                }
            }
            send_content = json.dumps(reply, ensure_ascii=False, indent=2)
            _do_reply( msg_type="post", reply_message=send_content)

        self.logger.info(f"[Reply sent] message_id={message_id}, reply={content[:100]}...")

    def _handle_message_receive(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """
        Handle message receive event

        Args:
            data: Feishu message event data
        """
        try:
            # Extract message info
            event = data.event
            message = event.message
            content = message.content
            chat_id = message.chat_id
            message_id = message.message_id
            sender = event.sender

            # Parse message content (Feishu messages are in JSON format)
            content_dict = json.loads(content)
            text = content_dict.get("text", "")

            if not text:
                return

            # Skip already replied messages to avoid long connection replay
            if message_id in self.task_db:
                self.logger.info(f"[Duplicate message] message_id={message_id} skipped")
                return

            final_text = text
            # Get mentions array (may be empty if no one is @mentioned)
            mentions = event.message.mentions

            if mentions:
                for mention in mentions:
                    key = mention.key
                    name = mention.name

                    final_text = final_text.replace(key, f"@{name}")


            self.logger.info(
                f"[Message received] chat_id={chat_id}, message_id={message_id}, "
                f"sender={sender.sender_id.user_id}, text={final_text}"
            )

            # Reply with reaction
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
            self.logger.error(f"Error processing message: {e}")
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
            self.logger.error(f"Failed to add reaction: code={response.code}, msg={response.msg}")
            return ""
        else:
            self.logger.debug("Reaction added successfully")
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
            self.logger.error(f"Failed to delete reaction: code={response.code}, msg={response.msg}")
        else:
            self.logger.debug("Reaction deleted successfully")


    def _reply_message(self, message_id: str, msg_type: str,reply: str):
        """
        Send a reply message to Feishu

        Args:
            chat_id: Chat ID
            text: Message text
        """

        try:
            request = ReplyMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(ReplyMessageRequestBody.builder()
                              .msg_type(msg_type) # Specify message type as text
                              .content(reply)  # Fill in JSON string
                              .build()) \
                .build()

            response = self.client2.im.v1.message.reply(request)

            if not response.success():
                raise Exception(
                    f"client.im.v1.message.reply failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")

        except Exception as e:
            self.logger.error(f"Error replying to message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _send_message(self, chat_id: str, text: str):
        """
        Send a message to Feishu

        Args:
            chat_id: Chat ID
            text: Message text
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
            self.logger.error(f"Error creating message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())


    def _upload_image(self, file_path: str) -> str | None:
        """Upload image to Feishu, return image key"""
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody
        try:
            with open(file_path, "rb") as f:
                request: CreateImageRequest = CreateImageRequest.builder() \
                    .request_body(CreateImageRequestBody.builder()
                                  .image_type("message")
                                  .image(f)
                                  .build()) \
                    .build()
                response: CreateImageResponse = self.client2.im.v1.image.create(request)
                if response.success():
                    image_key = response.data.image_key
                    logger.debug("Uploaded image {}: {}", os.path.basename(file_path), image_key)
                    return image_key
                else:
                    logger.error("Failed to upload image to Feishu: code={}, msg={}", response.code, response.msg)
        except Exception as e:
            logger.error("Error uploading image {}: {}", file_path, e)
            return None

    def _upload_file(self, file_path: str) -> str | None:
        """Upload file to Feishu, return file key"""
        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody,CreateFileResponse

        ext = os.path.splitext(file_path)[1].lower()
        file_type = self._FILE_TYPE_MAP.get(ext, "stream")
        file_name = os.path.basename(file_path)
        try:
            with open(file_path, "rb") as f:
                request: CreateFileRequest = CreateFileRequest.builder() \
                    .request_body(CreateFileRequestBody.builder()
                                  .file_type(file_type)
                                  .file_name(file_name)
                                  .file(f)
                                  .build()) \
                    .build()
                response: CreateFileResponse = self.client2.im.v1.file.create(request)
                if response.success():
                    file_key = response.data.file_key
                    logger.debug("Uploaded file {}: {}", file_name, file_key)
                    return file_key
                else:
                    logger.error("Failed to upload file to Feishu: code={}, msg={}", response.code, response.msg)
                    return None
        except Exception as e:
            logger.error("Error uploading file {}: {}", file_path, e)
            return None


    def start(self) -> None:
        """Start the bot"""
        self.logger.info("=" * 50)
        self.logger.info("Feishu long-connection bot starting...")
        self.logger.info(f"APP_ID: {FeishuBotConfig.FEISHU_APP_ID}")
        self.logger.info(f"Session timeout: {self.session_timeout} seconds")
        self.logger.info("=" * 50)

        try:
            self.client.start()
        except KeyboardInterrupt:
            self.logger.info("Bot stopped")
        except Exception as e:
            self.logger.error(f"Bot runtime error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())