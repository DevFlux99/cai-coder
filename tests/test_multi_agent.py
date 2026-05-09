"""
Unit tests for multi-agent collaboration system.

Tests: registry, factory, dispatcher, delegate_agent tool.
"""

import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from agent.multi_agent.registry import (
    AgentDefinition,
    AgentRegistry,
    agent_registry,
    _build_default_agents,
)
from agent.multi_agent.factory import AgentFactory
from agent.multi_agent.dispatcher import AgentDispatcher


# ============================================================
# Registry Tests
# ============================================================

class TestAgentRegistry:
    def test_default_agents_loaded(self):
        names = agent_registry.get_agent_names()
        assert "code-review" in names
        assert "bug-fix" in names
        assert "devops" in names
        assert "general" in names

    def test_get_existing_agent(self):
        agent = agent_registry.get("code-review")
        assert agent is not None
        assert agent.name == "code-review"
        assert "review" in agent.description.lower()
        assert len(agent.tools) > 0

    def test_get_nonexistent_agent(self):
        assert agent_registry.get("nonexistent") is None

    def test_register_custom_agent(self):
        registry = AgentRegistry()
        custom = AgentDefinition(
            name="test-agent",
            description="Test",
            system_prompt="Test prompt",
            tools=["bash"],
        )
        registry.register(custom)
        assert registry.get("test-agent") is not None
        assert "test-agent" in registry.get_agent_names()

    def test_disabled_agent_excluded(self):
        registry = AgentRegistry()
        agent_def = AgentDefinition(
            name="disabled-agent",
            description="Disabled",
            system_prompt="Test",
            enabled=False,
        )
        registry.register(agent_def)
        assert "disabled-agent" not in registry.get_agent_names()
        assert "disabled-agent" not in [
            a.name for a in registry.list_agents()
        ]

    def test_get_agent_descriptions(self):
        desc = agent_registry.get_agent_descriptions()
        assert "code-review" in desc
        assert "bug-fix" in desc
        assert "devops" in desc

    def test_list_agents_only_enabled(self):
        agents = agent_registry.list_agents()
        for a in agents:
            assert a.enabled is True


# ============================================================
# Factory Tests
# ============================================================

class TestAgentFactory:
    def _make_factory(self, tools=None):
        mock_llm = MagicMock()
        tool_map = {}
        if tools:
            for name in tools:
                t = MagicMock()
                t.name = name
                tool_map[name] = t
        return AgentFactory(llm=mock_llm, available_tools=tool_map)

    def test_build_agent(self):
        factory = self._make_factory(["bash", "read_file"])
        with patch("agent.multi_agent.factory.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agent = factory.build("code-review")
            assert agent is not None
            mock_create.assert_called_once()

    def test_build_nonexistent_agent(self):
        factory = self._make_factory()
        assert factory.build("nonexistent") is None

    def test_build_disabled_agent(self):
        factory = self._make_factory(["bash"])
        reg = agent_registry.get("code-review")
        reg.enabled = False
        try:
            assert factory.build("code-review") is None
        finally:
            reg.enabled = True

    def test_get_or_build_caches(self):
        factory = self._make_factory(["bash"])
        with patch("agent.multi_agent.factory.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            a1 = factory.get_or_build("code-review")
            a2 = factory.get_or_build("code-review")
            assert a1 is a2
            assert mock_create.call_count == 1

    def test_resolve_missing_tools_fallback(self):
        factory = self._make_factory()  # no tools
        with patch("agent.multi_agent.factory.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agent = factory.build("code-review")
            assert agent is not None

    def test_clear_cache(self):
        factory = self._make_factory(["bash"])
        with patch("agent.multi_agent.factory.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            factory.get_or_build("code-review")
            factory.clear_cache()
            factory.get_or_build("code-review")
            assert mock_create.call_count == 2

    def test_build_all(self):
        factory = self._make_factory(["bash", "read_file"])
        with patch("agent.multi_agent.factory.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agents = factory.build_all()
            assert len(agents) == len(agent_registry.list_agents())


# ============================================================
# Dispatcher Tests
# ============================================================

class TestAgentDispatcher:
    def _make_dispatcher(self, tools=None):
        factory_tools = {}
        if tools:
            for name in tools:
                t = MagicMock()
                t.name = name
                factory_tools[name] = t
        mock_llm = MagicMock()
        factory = AgentFactory(llm=mock_llm, available_tools=factory_tools)
        return AgentDispatcher(factory=factory, llm=mock_llm), factory

    def test_classify_task(self):
        disp, _ = self._make_dispatcher(["bash"])
        disp._llm.invoke = lambda msgs: MagicMock(content="bug-fix")
        result = disp.classify_task("fix this error")
        assert result == "bug-fix"

    def test_classify_task_invalid_fallback(self):
        disp, _ = self._make_dispatcher()
        disp._llm.invoke = lambda msgs: MagicMock(content="unknown-agent")
        result = disp.classify_task("random task")
        assert result == "general"

    def test_dispatch_with_explicit_agent(self):
        disp, factory = self._make_dispatcher(["bash"])
        mock_agent = MagicMock()
        mock_agent.invoke = lambda inp, config=None: {
            "messages": [
                HumanMessage(content="review code"),
                AIMessage(content="Code looks good!"),
            ]
        }
        factory._cache["code-review"] = mock_agent

        result = disp.dispatch("review this code", agent_name="code-review")
        assert result["agent"] == "code-review"
        assert result["response"] == "Code looks good!"
        assert result["message_count"] == 2

    def test_dispatch_auto_route(self):
        disp, factory = self._make_dispatcher(["bash"])
        disp._llm.invoke = lambda msgs: MagicMock(content="devops")
        mock_agent = MagicMock()
        mock_agent.invoke = lambda inp, config=None: {
            "messages": [AIMessage(content="Docker config updated")]
        }
        factory._cache["devops"] = mock_agent

        result = disp.dispatch("set up docker")
        assert result["agent"] == "devops"

    def test_dispatch_nonexistent_agent(self):
        disp, _ = self._make_dispatcher()
        result = disp.dispatch("task", agent_name="nonexistent")
        assert "error" in result

    def test_dispatch_agent_failure(self):
        disp, factory = self._make_dispatcher(["bash"])
        mock_agent = MagicMock()
        mock_agent.invoke = MagicMock(side_effect=RuntimeError("LLM error"))
        factory._cache["bug-fix"] = mock_agent

        result = disp.dispatch("fix bug", agent_name="bug-fix")
        assert "error" in result
        assert "LLM error" in result["error"]

    def test_dispatch_with_thread_id(self):
        disp, factory = self._make_dispatcher(["bash"])
        mock_agent = MagicMock()
        mock_agent.invoke = MagicMock(return_value={
            "messages": [AIMessage(content="done")]
        })
        factory._cache["general"] = mock_agent

        disp.dispatch("hello", agent_name="general", thread_id="thread-123")
        call_config = mock_agent.invoke.call_args[1].get("config")
        assert call_config is not None
        assert call_config["configurable"]["thread_id"] == "thread-123"


# ============================================================
# DelegateAgent Tool Tests
# ============================================================

class TestDelegateAgentTool:
    def _import_delegate_tool(self):
        """Import DelegateAgentTool bypassing tools/__init__.py circular import."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'agent.tools.delegate_agent',
            'agent/tools/delegate_agent.py'
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.DelegateAgentTool

    def test_tool_without_dispatcher(self):
        DelegateAgentTool = self._import_delegate_tool()
        tool = DelegateAgentTool()
        result = tool._run(task="test")
        assert "error" in result

    def test_tool_with_dispatcher(self):
        DelegateAgentTool = self._import_delegate_tool()
        tool = DelegateAgentTool()

        mock_llm = MagicMock()
        factory = AgentFactory(
            llm=mock_llm,
            available_tools={"bash": MagicMock(name="bash")},
        )
        mock_agent = MagicMock()
        mock_agent.invoke = lambda inp, config=None: {
            "messages": [AIMessage(content="Fixed!")]
        }
        factory._cache["bug-fix"] = mock_agent

        disp = AgentDispatcher(factory=factory, llm=mock_llm)
        tool.set_dispatcher(disp)

        result = tool._run(task="fix the null pointer error", agent_name="bug-fix")
        assert result["agent"] == "bug-fix"
        assert result["response"] == "Fixed!"
