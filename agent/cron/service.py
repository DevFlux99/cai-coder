import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from datetime import datetime
from agent.utils.common_util import ensure_dir
from agent.utils.logger import get_logger

log = get_logger("cron_service")

# ================= Data Models ================

@dataclass
class CronSchedule:
    kind: str  # "every" (periodic execution) , "at" (one-time execution), "cron": cron expression
    every_ms: int = 0  # interval in milliseconds for periodic execution
    at_ms: int = 0  # absolute timestamp (in milliseconds) for one-time execution
    expr: str | None = None # For "cron": cron expression (e.g. "0 9 * * *") 。

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "every_ms": self.every_ms,
            "at_ms": self.at_ms,
            "expr": self.expr
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CronSchedule":
        return cls(
            kind=data["kind"],
            every_ms=data.get("every_ms", 0),
            at_ms=data.get("at_ms", 0),
            expr=data.get("expr"),
        )

@dataclass
class CronJobState:
    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "next_run_at_ms": self.next_run_at_ms,
            "last_run_at_ms": self.last_run_at_ms,
            "last_status": self.last_status,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CronJobState":
        return cls(
            next_run_at_ms=data.get("next_run_at_ms"),
            last_run_at_ms=data.get("last_run_at_ms"),
            last_status=data.get("last_status"),
            last_error=data.get("last_error"),
        )


@dataclass
class CronJob:
    id: str = field(default_factory=lambda :str(uuid.uuid4())[:8])
    name: str = ""
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=CronSchedule)
    state: CronJobState = field(default_factory=CronJobState)
    payload: Any = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "schedule": self.schedule.to_dict(),
            "state": self.state.to_dict(),
            "payload": self.payload,  # Note: payload must be serializable
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CronJob":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            schedule=CronSchedule.from_dict(data.get("schedule", {})),
            state=CronJobState.from_dict(data.get("state", {})),
            payload=data.get("payload"),
        )


def _now_ms() -> int:
    """Get the current time in milliseconds timestamp"""
    return int(time.time() * 1000)

def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Calculate the absolute timestamp for the next execution"""
    if schedule.kind == "every":
       if schedule.every_ms <= 0:
           return None
       return now_ms + schedule.every_ms
    elif schedule.kind == "at":
        # If the execution time has passed, return None to indicate no further execution
        return schedule.at_ms if schedule.at_ms > now_ms else None
    elif schedule.kind == "cron":
        from croniter import croniter

        base_time = now_ms / 1000
        base_date = datetime.fromtimestamp(base_time)
        cron = croniter(schedule.expr,base_date)
        next_date = cron.get_next(datetime)
        return int(next_date.timestamp() * 1000)

    return None

class CronService:

    def __init__(
            self,
            workspace: Path,
            on_job: Callable[[CronJob], None] | None = None,
            max_sleep_ms: int = 300_000
    ):
        self.workspace = workspace
        self.cron_dir = ensure_dir(self.workspace / "cron")
        self.on_job = on_job
        self.max_sleep_ms = max_sleep_ms

        self._jobs: list[CronJob] = []
        self._lock = threading.RLock()  # Thread-safe protection for _jobs list
        self._condition = threading.Condition(self._lock)

        self._running = False
        self._thread: threading.Thread | None = None


    def _get_corn_job_path(self):
        return self.cron_dir / "cron.json"

    def _load(self) -> list[CronJob]:
        cron_path = self._get_corn_job_path()

        if not cron_path.exists():
            return []

        try:
            with open(cron_path, encoding="utf-8") as f:
                body = f.read() or "[]"
            raw: list[Any] = json.loads(body)
        except Exception as e:
            log.warning(f"Failed to read corn job path {cron_path}: {e}")
            return []

        return [CronJob.from_dict(v) for v in raw]

    def start(self):
        """Start background scheduled thread"""
        if self._running:
            return
        self._running = True
        self._jobs = self._load()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("Cron service started.")

    def stop(self):
        if not self._running:
            log.info("Cron service already stopped.")
            return
        with self._condition:
            self._running = False
            self._condition.notify_all() # Wake up possibly sleeping threads and make them exit

        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("Cron service stopped.")

    def _run_loop(self):
        """Main loop of the background thread: dynamic sleep + triggered execution"""
        while self._running:
            next_wake_ms = self._get_next_wake_ms()

            if next_wake_ms is None:
                delay_ms = self.max_sleep_ms
            else:
                delay_ms = min(self.max_sleep_ms, max(0, next_wake_ms - _now_ms()))

            delay_s = delay_ms / 1000.0

            with self._condition:
                self._condition.wait(timeout=delay_s)

            if not self._running:
                break

            self._on_timer()

    def _on_timer(self):
        """Time's up, scan and execute expired tasks"""
        due_jobs = []
        with self._lock:
            now = _now_ms()
            for job in self._jobs:
                if job.enabled and job.state.next_run_at_ms and now >= job.state.next_run_at_ms:
                    due_jobs.append(job)


        for job in due_jobs:
            self._execute_job(job)

    def _execute_job(self, job: CronJob) -> None:
        """Execute a single task and update status"""
        start_ms = _now_ms()
        log.info(f"Cron: executing job '{job.name}' ({job.id})")

        try:
            if self.on_job:
                self.on_job(job)
            last_status = "ok"
            last_error = None
        except Exception as e:
            last_status = "error"
            last_error = str(e)
            log.error(f"Cron: job '{job.name}' failed: {e}")

        with self._lock:
            job.state.last_status = last_status
            job.state.last_error = last_error
            job.state.last_run_at_ms = start_ms

            if job.schedule.kind == "at":
                job.enabled = False
                job.state.next_run_at_ms = None
            else:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

            self._save()

    def _get_next_wake_ms(self):

        with self._lock:
            times = [
                job.state.next_run_at_ms for job in self._jobs
                if job.enabled and job.state.next_run_at_ms
            ]
            return min(times) if times else None

    def _save(self) -> None:
        corn_path = self._get_corn_job_path()
        with self._lock:
            joblist = [item.to_dict() for item in self._jobs]
            data = json.dumps(joblist,ensure_ascii=False, indent=2)
            with open(corn_path, 'w', encoding='utf-8') as f:
                f.write(data)

    # ========== Public CRUD API ==========
    def add_job(self, name: str, schedule: CronSchedule, payload: Any=None) -> CronJob:

        job = CronJob(
            name=name,
            schedule=schedule,
            payload=payload,
            state=CronJobState(
                next_run_at_ms=_compute_next_run(schedule, _now_ms())
            )
        )

        # [Key fix] Lock list modification and notify to wake up background thread
        with self._condition:
            self._jobs.append(job)
            self._save()
            self._condition.notify()

        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove Task"""
        with self._condition:
            before_len = len(self._jobs)
            self._jobs = [job for job in self._jobs if job.id != job_id]
            changed = len(self._jobs) < before_len
            if changed:
                self._save()
                self._condition.notify()
            return changed

    def list_jobs(self) -> list[CronJob]:
        """Get all task lists"""
        with self._lock:
            return list(self._jobs)