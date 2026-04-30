import os
import re
import tempfile
import threading
from pathlib import Path

from agent.utils.common_util import ensure_dir
from agent.utils.logger import get_logger

log = get_logger("memory_manager")

_L3_SUBDIRS = ("projects", "knowledge", "decisions", "lessons", "journal")

class MemoryManager:
    """Thread-safe manager for three-layer long-term memory.

    L1: memory/logs/YYYY-MM-DD.md  -- raw session logs
    L2: memory/this-week.md, memory/this-month.md  -- rolling summaries
    L3: long-term/  -- persistent knowledge, profile, rules, etc.
    """
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.logs_dir = ensure_dir(self.memory_dir / "logs")
        self.long_term_dir = ensure_dir(workspace / "long-term")
        for sub in _L3_SUBDIRS:
            ensure_dir(self.long_term_dir / sub)

        self._lock = threading.RLock()



    def _l3_file(self, name: str) -> Path:
        return self.long_term_dir / name


    def read_profile(self) -> str:
        return self._safe_read(self._l3_file("profile.md"))

    def read_preferences(self) -> str:
        return self._safe_read(self._l3_file("preferences.md"))

    def read_rules(self) -> str:
        return self._safe_read(self._l3_file("rules.md"))

    def read_glossary(self) -> str:
        return self._safe_read(self._l3_file("glossary.md"))

    def read_agent_index(self) -> str:
        return self._safe_read(self._l3_file("AGENT.md"))


    def update_profile(self, key:str, value:str) -> None:
        with self._lock:
            self._append_or_update_section(
                self._l3_file("profile.md"), key, value
            )
        log.debug(f"Profile updated: {key}")

    def update_preferences(self, key: str, value: str) -> None:
        with self._lock:
            self._append_or_update_section(
                self._l3_file("preferences.md"), key, value
            )
        log.debug(f"Preferences updated: {key}")

    def update_glossary(self, term: str, definition: str) -> None:
        with self._lock:
            self._append_or_update_section(
                self._l3_file("glossary.md"), term, definition
            )
        log.debug(f"Glossary updated: {term}")

    # ──────────────── Internal Helpers ────────────────

    def _safe_read(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"Failed to read {path}: {e}")
            return ""


    def _atomic_write(self, path: Path, content: str) -> None:
        dir_path = path.parent
        dir_path.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _append_or_update_section(self, path: Path, heading: str, content: str) -> None:
        """Find '## {heading}' in markdown, replace content below it; or append new section."""
        raw = ""
        if path.exists():
            raw = path.read_text(encoding="utf-8")

        pattern = re.compile(
            rf"(^##\s+{re.escape(heading)}\s*\n)(.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )

        if pattern.search(raw):
            new_raw = pattern.sub(rf"\1{content}\n", raw)
        else:
            new_raw = raw.rstrip() + f"\n\n## {heading}\n{content}\n"

        self._atomic_write(path, new_raw)