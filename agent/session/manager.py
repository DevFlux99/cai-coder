import json
import os
import tempfile
import threading
from datetime import datetime
from dataclasses import field, dataclass, asdict
from pathlib import Path
from typing import Any

from agent.utils.common_util import ensure_dir
from agent.utils.logger import get_logger

log = get_logger("session_manager")


@dataclass
class Session:

    key: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            key=data["key"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class SessionManager:

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self._cache: dict[str, Session] = self._load()
        self._lock = threading.Lock()

    def _get_session_path(self) -> Path:
        return self.sessions_dir / "sessions.json"

    def get_or_create(self, key: str) -> Session:
        """
        Get existing session or create and return
        :param key: Session key (channel:chat_id).
        :return: Session
        """
        with self._lock:
            if key in self._cache:
                return self._cache[key]

            session = Session(key=key)
            self._cache[key] = session
            self._save()
            return session

    def _load(self) -> dict[str, Session]:
        session_path = self._get_session_path()

        if not session_path.exists():
            return {}

        try:
            with open(session_path, encoding="utf-8") as f:
                body = f.read() or "{}"
            raw: dict[str, dict] = json.loads(body)
        except Exception as e:
            log.warning(f"Failed to read session path {session_path}: {e}")
            return {}

        return {k: Session.from_dict(v) for k, v in raw.items()}

    def _save(self):
        session_path = self._get_session_path()
        cache_to_save = {k: v.to_dict() for k, v in self._cache.items()}
        data = json.dumps(cache_to_save, ensure_ascii=False, indent=2)
        dir_path = session_path.parent
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(data)
            os.replace(tmp_path, session_path)
        except Exception:
            os.unlink(tmp_path)
            raise

    def list_sessions(self) -> list[Session]:
        sessions = self._cache.values()
        return sorted(sessions, key=lambda x: x.updated_at, reverse=True)
