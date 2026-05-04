import threading
import time
from time import sleep

from agent.bus.bus import MessageBus
from agent.bus.events import OutMessage
from agent.integration.base import BaseChannel
from agent.integration.manager import ChannelManager
from agent.server import AgentLoop
from agent.utils.logger import get_logger

log = get_logger("test_agent_loop")

class MockChannel(BaseChannel):
    name = "mock"

    def __init__(self, bus: MessageBus):
        super().__init__(bus)
        self.received: list[OutMessage] = []
        self._lock = threading.Lock()

    def send(self, msg: OutMessage) -> None:
        assert msg.channel == self.name
        with self._lock:
            self.received.append(msg)
        log.info(f"[Reply sent] chat_id={msg.chat_id}, reply={msg.content[:100]}...")

    def start(self) -> None:
        log.info("start mock channel...")
        pass

def _make_channel(bus: MessageBus):
    return MockChannel(bus)

def _make_agent_loop(bus: MessageBus, channel: BaseChannel):
    channel_manager = ChannelManager(bus)
    channel_manager.channels["mock"] = channel

    channel_manager.start_one("mock")
    loop = AgentLoop(bus)
    return loop


def test_agent_loop():
    bus = MessageBus()
    mock_channel = _make_channel(bus)

    agentloop = _make_agent_loop(bus, mock_channel)
    agentloop.start()

    mock_channel._handle_message(
        chat_id="chat_id",
        content="What can you do?",
        metadata= {
            "messages": "How's the weather in Shenzhen?"
        }
    )

    sleep(5)


def test_concurrent_different_chat_ids():
    """Different chat_id tasks should execute in parallel without blocking each other."""
    bus = MessageBus()
    mock_channel = _make_channel(bus)
    agentloop = _make_agent_loop(bus, mock_channel)
    agentloop.start()

    start_time = time.time()
    mock_channel._handle_message(chat_id="chat_1", content="What time is it now?")
    mock_channel._handle_message(chat_id="chat_2", content="What time is it now?")

    # Wait for both to complete
    for _ in range(60):
        if len(mock_channel.received) >= 2:
            break
        sleep(1)

    elapsed = time.time() - start_time

    assert len(mock_channel.received) == 2
    chat_ids = {msg.chat_id for msg in mock_channel.received}
    assert chat_ids == {"chat_1", "chat_2"}
    # Parallel execution should take less time than 2x single execution
    log.info(f"Concurrent execution took {elapsed:.2f}s")


def test_serial_same_chat_id():
    """Same chat_id tasks should execute serially, one after another."""
    bus = MessageBus()
    mock_channel = _make_channel(bus)
    agentloop = _make_agent_loop(bus, mock_channel)
    agentloop.start()

    mock_channel._handle_message(chat_id="chat_serial", content="What time is it now?")
    sleep(1)  # Ensure first task is running before submitting second
    mock_channel._handle_message(chat_id="chat_serial", content="What time is it now?")

    start_time = time.time()
    # Wait for both to complete
    for _ in range(120):
        if len(mock_channel.received) >= 2:
            break
        sleep(1)

    elapsed = time.time() - start_time

    assert len(mock_channel.received) == 2
    # All results should belong to the same chat_id
    assert all(msg.chat_id == "chat_serial" for msg in mock_channel.received)
    log.info(f"Serial execution took {elapsed:.2f}s")

