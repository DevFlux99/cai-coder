import os

import pytest

from agent.memory.manager import MemoryManager, _L3_SUBDIRS


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