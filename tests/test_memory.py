import os
from pathlib import Path

import pytest

from agent.memory.manager import MemoryManager, _L3_SUBDIRS
from agent.memory.template import SESSION_LOG_ENTRY
from agent.utils.common_util import ensure_dir


class TestMemoryManagerInit:
    """测试 MemoryManager 初始化"""

    def test_creates_memory_directory(self, tmp_path):
        manager = MemoryManager(tmp_path)
        assert manager.memory_dir.exists()
        assert manager.memory_dir.is_dir()

    def test_creates_logs_directory(self, tmp_path):
        manager = MemoryManager(tmp_path)
        assert manager.logs_dir.exists()
        assert manager.logs_dir == tmp_path / "memory" / "logs"

    def test_creates_long_term_directory(self, tmp_path):
        manager = MemoryManager(tmp_path)
        assert manager.long_term_dir.exists()
        assert manager.long_term_dir == tmp_path / "long-term"

    def test_creates_all_l3_subdirectories(self, tmp_path):
        manager = MemoryManager(tmp_path)
        for sub in _L3_SUBDIRS:
            sub_dir = manager.long_term_dir / sub
            assert sub_dir.exists(), f"子目录 {sub} 不存在"
            assert sub_dir.is_dir()

    def test_existing_workspace_still_works(self, tmp_path):
        """已有目录结构时不应报错"""
        (tmp_path / "memory" / "logs").mkdir(parents=True)
        (tmp_path / "long-term" / "projects").mkdir(parents=True)
        manager = MemoryManager(tmp_path)
        assert manager.memory_dir.exists()

    def test_lock_is_reentrant(self, tmp_path):
        import threading
        manager = MemoryManager(tmp_path)

        # 验证它在同一个线程内可以多次获取（这是 RLock 的核心特征，普通 Lock 会死锁）
        with manager._lock:
            # 如果是普通的 Lock，下面这行会永远阻塞卡死；如果是 RLock 则能顺利通过
            manager._lock.acquire()
            manager._lock.release()


class TestSafeRead:
    """测试 _safe_read 方法"""

    def test_returns_empty_string_for_nonexistent_file(self, tmp_path):
        manager = MemoryManager(tmp_path)
        result = manager._safe_read(tmp_path / "nonexistent.md")
        assert result == ""

    def test_reads_existing_file_correctly(self, tmp_path):
        manager = MemoryManager(tmp_path)
        test_file = tmp_path / "test.md"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = manager._safe_read(test_file)
        assert result == "Hello, World!"

    def test_returns_empty_string_on_permission_error(self, tmp_path):
        manager = MemoryManager(tmp_path)
        test_file = tmp_path / "restricted.md"
        test_file.write_text("secret", encoding="utf-8")

        # 移除读取权限（仅限 Unix）
        if os.name != "nt":
            test_file.chmod(0o000)
            result = manager._safe_read(test_file)
            assert result == ""
            # 恢复权限以便清理
            test_file.chmod(0o644)

    def test_handles_empty_file(self, tmp_path):
        manager = MemoryManager(tmp_path)
        test_file = tmp_path / "empty.md"
        test_file.write_text("", encoding="utf-8")

        result = manager._safe_read(test_file)
        assert result == ""

    def test_handles_unicode_content(self, tmp_path):
        manager = MemoryManager(tmp_path)
        test_file = tmp_path / "unicode.md"
        content = "hello world"
        test_file.write_text(content, encoding="utf-8")

        result = manager._safe_read(test_file)
        assert result == content

class TestReadProfileMethods:
    """测试各种读取方法"""

    @pytest.fixture
    def manager_with_data(self, tmp_path):
        manager = MemoryManager(tmp_path)
        # 写入各文件
        (manager.long_term_dir / "profile.md").write_text("Profile content", encoding="utf-8")
        (manager.long_term_dir / "preferences.md").write_text("Preferences content", encoding="utf-8")
        (manager.long_term_dir / "rules.md").write_text("Rules content", encoding="utf-8")
        (manager.long_term_dir / "glossary.md").write_text("Glossary content", encoding="utf-8")
        (manager.long_term_dir / "AGENT.md").write_text("Agent index content", encoding="utf-8")
        return manager

    def test_read_profile(self, manager_with_data):
        assert manager_with_data.read_profile() == "Profile content"

    def test_read_preferences(self, manager_with_data):
        assert manager_with_data.read_preferences() == "Preferences content"

    def test_read_rules(self, manager_with_data):
        assert manager_with_data.read_rules() == "Rules content"

    def test_read_glossary(self, manager_with_data):
        assert manager_with_data.read_glossary() == "Glossary content"

    def test_read_agent_index(self, manager_with_data):
        assert manager_with_data.read_agent_index() == "Agent index content"

    def test_read_returns_empty_when_missing(self, tmp_path):
        manager = MemoryManager(tmp_path)
        assert manager.read_profile() == ""
        assert manager.read_preferences() == ""
        assert manager.read_rules() == ""
        assert manager.read_glossary() == ""
        assert manager.read_agent_index() == ""

class TestAtomicWrite:
    """测试 _atomic_write 方法"""

    def test_writes_new_file(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "new_file.md"

        manager._atomic_write(target, "new content")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "new content"

    def test_overwrites_existing_file(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "existing.md"
        target.write_text("old content", encoding="utf-8")

        manager._atomic_write(target, "new content")

        assert target.read_text(encoding="utf-8") == "new content"

    def test_creates_parent_directories(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "deep" / "nested" / "file.md"

        manager._atomic_write(target, "nested content")

        assert target.exists()
        assert target.read_text(encoding="utf-8") == "nested content"

    def test_no_temp_file_left_on_success(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "clean.md"

        manager._atomic_write(target, "content")

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestAppendOrUpdateSection:
    """测试 _append_or_update_section 方法"""

    def test_creates_new_file_with_section(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "new.md"

        manager._append_or_update_section(target, "Skills", "Python, Go")

        content = target.read_text(encoding="utf-8")
        assert "## Skills" in content
        assert "Python, Go" in content


    def test_appends_new_section_to_existing_file(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "existing.md"
        target.write_text("## Background\nSome background info\n", encoding="utf-8")

        manager._append_or_update_section(target, "Skills", "Python, Go")

        content = target.read_text(encoding="utf-8")
        assert "## Background" in content
        assert "## Skills" in content
        assert "Python, Go" in content

    def test_updates_existing_section(self, tmp_path):
        manager = MemoryManager(tmp_path)
        target = tmp_path / "update.md"
        target.write_text(
            "## Skills\nOld skills\n\n## Other\nOther info\n",
            encoding="utf-8"
        )

        manager._append_or_update_section(target, "Skills", "New skills")

        content = target.read_text(encoding="utf-8")
        assert "New skills" in content
        assert "Old skills" not in content
        assert "## Other" in content
        assert "Other info" in content


class TestGetMemoryContext:
    """测试 get_memory_context 方法"""

    def test_returns_empty_string_when_all_files_missing(self, tmp_path):
        """所有文件都不存在时返回空字符串"""
        manager = MemoryManager(tmp_path)
        result = manager.get_memory_context()
        assert result == ""

    def test_returns_empty_string_when_all_files_empty(self, tmp_path):
        """所有文件都存在但内容为空时返回空字符串"""
        manager = MemoryManager(tmp_path)
        (manager.long_term_dir / "profile.md").write_text("", encoding="utf-8")
        (manager.long_term_dir / "preferences.md").write_text("", encoding="utf-8")
        (manager.long_term_dir / "rules.md").write_text("", encoding="utf-8")

        result = manager.get_memory_context()
        assert result == ""

    def test_includes_only_files_with_content(self, tmp_path):
        """只拼接有实际内容的文件"""
        manager = MemoryManager(tmp_path)
        (manager.long_term_dir / "profile.md").write_text("Name: Alice", encoding="utf-8")
        # preferences.md 不创建或保持空
        (manager.long_term_dir / "rules.md").write_text("Be polite", encoding="utf-8")

        result = manager.get_memory_context()

        assert "### profile" in result
        assert "Name: Alice" in result
        assert "### rules" in result
        assert "Be polite" in result
        # 关键断言：不应该包含 preferences 的标题
        assert "### preferences" not in result

    def test_maintains_correct_order(self, tmp_path):
        """必须严格按照 profile -> preferences -> rules 的顺序输出"""
        manager = MemoryManager(tmp_path)
        # 故意倒序写入，避免巧合通过
        (manager.long_term_dir / "rules.md").write_text("Rules", encoding="utf-8")
        (manager.long_term_dir / "profile.md").write_text("Profile", encoding="utf-8")
        (manager.long_term_dir / "preferences.md").write_text("Prefs", encoding="utf-8")

        result = manager.get_memory_context()

        profile_idx = result.index("### profile")
        prefs_idx = result.index("### preferences")
        rules_idx = result.index("### rules")

        assert profile_idx < prefs_idx < rules_idx

class TestAppendSessionLog:
    def test_template_contains_all_placeholders(self):
        """验证模板包含所有必要的占位符"""
        expected_placeholders = [
            "{session_id}",
            "{timestamp}",
            "{summary}",
            "{decisions}",
            "{errors}",
        ]
        for placeholder in expected_placeholders:
            assert placeholder in SESSION_LOG_ENTRY, \
                f"Missing placeholder: {placeholder}"

    def test_template_format_with_sample_data(self):
        """验证模板能正确格式化"""
        result = SESSION_LOG_ENTRY.format(
            session_id="sess_001",
            timestamp="2024-01-15 10:30:00",
            summary="Test summary",
            decisions="Decision A; Decision B",
            errors="Error X",
        )
        assert "sess_001" in result
        assert "2024-01-15 10:30:00" in result
        assert "Test summary" in result
        assert "Decision A; Decision B" in result
        assert "Error X" in result
        assert "**Time**:" in result
        assert "**Summary**:" in result


    def test_returns_path_with_correct_date_format(self, tmp_path):
        from datetime import  date
        manager = MemoryManager(tmp_path)
        path = manager._today_log_path()

        assert isinstance(path, Path)
        assert path.parent == tmp_path / "memory" / "logs"
        assert path.name == date.today().strftime("%Y-%m-%d") + ".md"


    def test_creates_new_file_when_not_exists(self, tmp_path):
        """当文件不存在时，应创建新文件并写入 header + entry"""
        from datetime import  date

        filename = date.today().strftime("%Y-%m-%d") + ".md"

        file_path = tmp_path / "memory" / "logs" / filename
        assert not file_path.exists()

        manager = MemoryManager(tmp_path)
        path = manager.append_session_log(
                session_id="sess_123",
                summary="Initial session",
                decisions=["Use Python", "Use pytest"],
                errors=["Minor warning"],
            )


        assert path == str(file_path)

        written_content = file_path.read_text()
        assert "# Session Logs - " + date.today().strftime("%Y-%m-%d") in written_content
        assert "sess_123" in written_content

    def test_appends_to_existing_file(self,tmp_path):
        """当文件已存在时，应追加 entry 而不重写 header"""
        from datetime import  date

        datestr = str(date.today().strftime("%Y-%m-%d"))
        filename = datestr + ".md"
        ensure_dir(tmp_path / "memory" / "logs")
        file_path = tmp_path / "memory" / "logs" / filename

        file_path.write_text(f"# Session Logs - {datestr}\n", encoding="utf-8")

        manager = MemoryManager(tmp_path)
        path = manager.append_session_log(
                session_id="sess_456",
                summary="Second session",
                decisions=["Continue"],
                errors=[],
            )
        assert path == str(file_path)

        content = file_path.read_text(encoding="utf-8")
        assert "# Session Logs - " + date.today().strftime("%Y-%m-%d") in content
        assert "sess_456" in content

    def test_multiple_decisions_joined_by_semicolon(self, tmp_path):
        """多个 decisions 应用分号连接"""

        manager = MemoryManager(tmp_path)
        result = manager.append_session_log(
                session_id="sess_multi",
                summary="session",
                decisions=["Dec A", "Dec B", "Dec C"],
                errors=["Error 1", "Error 2"],
            )
        file_path = Path(result)
        written_content = file_path.read_text()
        assert "**Key Decisions**: Dec A; Dec B; Dec C" in written_content
        assert "**Errors/Issues**: Error 1; Error 2" in written_content

    def test_empty_decisions_shows_none(self, tmp_path):
        """decisions 为空列表时，应显示 'None'"""

        manager = MemoryManager(tmp_path)
        result = manager.append_session_log(
                session_id="sess_empty",
                summary="Test",
                decisions=[],
                errors=[],
            )
        file_path = Path(result)
        written_content = file_path.read_text()
        assert "**Key Decisions**: None" in written_content
        assert "**Errors/Issues**: None" in written_content

# ==================== helper ====================
def _read(path:str) -> str:
    return Path(path).read_text(encoding="utf-8")

# ==================== add_lesson ====================

class TestAddLesson:
    def test_creates_file_with_correct_path(self, tmp_path):
        from datetime import  date

        manager = MemoryManager(tmp_path)
        path = manager.add_lesson(
            task="Fix memory leak",
            mistake="Forgot to close connection",
            solution="Add context manager",
        )
        datestr = date.today().strftime("%Y-%m-%d")
        expected_name = f"{datestr}-Fix-memory-leak.md"
        assert path.endswith(f"lessons/{expected_name}")

    def test_file_content_matches_template(self, tmp_path):
        from datetime import  date

        manager = MemoryManager(tmp_path)
        path = manager.add_lesson(
            task="Fix memory leak",
            mistake="Forgot to close connection",
            solution="Add context manager",
        )
        content = _read(path)
        datestr = date.today().strftime("%Y-%m-%d")
        assert "# Lesson: Fix memory leak" in content
        assert f"**Date**: {datestr}" in content
        assert "**Task**: Fix memory leak" in content
        assert "**Mistake**: Forgot to close" in content
        assert "**Solution**: Add context manager" in content


    def test_slug_truncation_and_strip(self, tmp_path):
        """slug 应被截断到 20 字符并去掉首尾的 '-'"""
        from datetime import  date

        long_task = "!!!This is a very long task name that should be truncated!!!"

        manager = MemoryManager(tmp_path)
        path = manager.add_lesson(task=long_task, mistake="m", solution="s")

        filename = Path(path).name
        datestr = date.today().strftime("%Y-%m-%d")
        # 日期前缀 "2026-05-01-" 占 11 字符，slug 部分应 <= 20 字符
        slug_part = filename.replace(f"{datestr}-", "").replace(".md", "")
        assert len(slug_part) <= 20
        assert not slug_part.startswith("-")
        assert not slug_part.endswith("-")

    def test_chinese_characters_in_task(self, tmp_path):

        manager = MemoryManager(tmp_path)
        path = manager.add_lesson(
            task="修复内存泄漏问题",
            mistake="忘记关闭连接",
            solution="添加上下文管理器",
        )
        content = _read(path)
        assert "修复内存泄漏问题" in content

    def test_special_characters_replaced_by_dash(self, tmp_path):
        """替换特殊字符"""
        from datetime import  date

        manager = MemoryManager(tmp_path)
        path = manager.add_lesson(
            task="Hello@World#Test",
            mistake="m",
            solution="s",
        )
        filename = Path(path).name
        datestr = date.today().strftime("%Y-%m-%d")
        slug = filename.replace(f"{datestr}-", "").replace(".md", "")
        assert "@" not in slug
        assert "#" not in slug

# ==================== add_decision ====================
class TestAddDecision:

    def test_creates_file_with_correct_path(self, tmp_path):
        from datetime import  date

        manager = MemoryManager(tmp_path)
        path = manager.add_decision(
            topic="Choose database",
            context="Need low latency",
            decision="Use Redis",
            rationale="Sub-ms latency",
        )

        datestr = date.today().strftime("%Y-%m-%d")
        assert path.endswith(f"decisions/{datestr}-Choose-database.md")


    def test_file_content_matches_template(self, tmp_path):
        from datetime import  date

        manager = MemoryManager(tmp_path)
        path = manager.add_decision(
            topic="Choose DB",
            context="High concurrency",
            decision="PostgresSQL",
            rationale="Mature and reliable",
        )
        content = _read(path)
        datestr = date.today().strftime("%Y-%m-%d")
        assert "# Decision: Choose DB" in content
        assert f"**Date**: {datestr}" in content
        assert "**Context**: High concurrency" in content
        assert "**Decision**: PostgresSQL" in content
        assert "**Rationale**: Mature and reliable" in content

    def test_slug_truncation(self, tmp_path):

        manager = MemoryManager(tmp_path)
        long_topic = "a" * 50
        path = manager.add_decision(
            topic=long_topic, context="c", decision="d", rationale="r",
        )
        slug_part = Path(path).stem.split("-", 3)[-1]
        assert len(slug_part) <= 20

# ==================== add_knowledge ====================
class TestAddKnowledge:
    def test_creates_file_with_correct_path(self, tmp_path):
        # 不带日期前缀，slug 长度限制 30
        manager = MemoryManager(tmp_path)
        path = manager.add_knowledge(
            topic="Python GIL",
            content="The GIL prevents true parallel threads.",
        )
        assert path.endswith("knowledge/Python-GIL.md")

    def test_file_content_matches_template(self, tmp_path):

        manager = MemoryManager(tmp_path)
        path = manager.add_knowledge(
            topic="Python GIL",
            content="The GIL prevents true parallel threads."
        )
        content = _read(path)
        assert "# Knowledge: Python GIL" in content
        assert "The GIL prevents true parallel threads." in content

    def test_slug_truncation_30(self, tmp_path):

        manager = MemoryManager(tmp_path)
        long_topic = "Understanding distributed systems and consensus algorithms"
        path = manager.add_knowledge(topic=long_topic, content="c")
        slug = Path(path).stem
        assert len(slug) <= 30

# ==================== add_project ====================
class TestAddProject:

    def test_creates_file_with_correct_path(self, tmp_path):

        manager = MemoryManager(tmp_path)
        path = manager.add_project(
            name="My Awesome Project",
            background="A CLI tool for X",
        )
        assert path.endswith("projects/My-Awesome-Project.md")

    def test_file_content_matches_template(self, tmp_path):
        from datetime import date

        manager = MemoryManager(tmp_path)
        path = manager.add_project(
            name="Proj X",
            background="This is a cool project.",
        )

        content = _read(path)
        datestr = date.today().strftime("%Y-%m-%d")
        assert "# Project: Proj X" in content
        assert f"Last Updated: {datestr}" in content
        assert "This is a cool project." in content

    def test_slug_truncation_30(self, tmp_path):

        manager = MemoryManager(tmp_path)
        long_name = "N" * 60
        path = manager.add_project(name=long_name, background="bg")
        slug = Path(path).stem
        assert len(slug) <= 30

# ==================== add_journal_entry ====================
class TestAddJournalEntry:
    def test_creates_new_journal_file(self, tmp_path):
        from datetime import date, datetime

        manager = MemoryManager(tmp_path)
        path = manager.add_journal_entry("First entry today.")
        content = _read(path)
        datestr = date.today().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%H:%M")
        assert f"# Journal - {datestr}" in content
        assert f"## {now}" in content
        assert "First entry today." in content


    def test_appends_to_existing_journal(self, tmp_path):
        from datetime import date

        manager = MemoryManager(tmp_path)
        # 第一次写入
        path1 = manager.add_journal_entry("Morning entry.")
        # 同一天第二次写入
        path2 = manager.add_journal_entry("Afternoon entry.")
        assert path1 == path2  # 同一个文件
        content = _read(path1)
        assert "Morning entry." in content
        assert "Afternoon entry." in content
        # 只有一个 journal header
        datestr = date.today().strftime("%Y-%m-%d")
        assert content.count(f"# Journal - {datestr}") == 1

    def test_append_preserves_order(self, tmp_path):

        manager = MemoryManager(tmp_path)
        manager.add_journal_entry("First")
        manager.add_journal_entry("Second")
        path = manager.add_journal_entry("Third")
        content_list = _read(path)
        assert content_list.index("First") < content_list.index("Second")
        assert content_list.index("Second") < content_list.index("Third")