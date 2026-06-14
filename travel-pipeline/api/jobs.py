"""in-memory Job Queue (MVP).

Redis 없이 순수 Python dict + threading.Lock 으로 구현.
⚠️ 서버 재시작 시 작업 기록은 모두 사라진다 (의도된 MVP 동작, 영구 저장은 Phase 3).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    job_type: str  # "storyboard" | "video"
    status: JobStatus
    progress: int = 0       # 0-100
    current_step: str = ""
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "progress": self.progress,
            "current_step": self.current_step,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create_job(self, job_type: str) -> Job:
        job = Job(
            job_id=str(uuid.uuid4()),
            job_type=job_type,
            status=JobStatus.PENDING,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def start_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.RUNNING

    def update_progress(self, job_id: str, progress: int, step: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = max(0, min(100, progress))
                job.current_step = step

    def complete_job(self, job_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.result = result
                job.current_step = "완료"

    def fail_job(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error = error

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active_job(self) -> Job | None:
        """대시보드 노드그래프용 읽기 전용 조회(기존 로직 무수정).

        진행 중(running/pending) 중 created_at 최신 1건, 없으면 가장 최근 job
        (완료 포함, 유휴 시 '마지막 완료' 표시용), 아무 job 도 없으면 None.
        """
        with self._lock:
            jobs = list(self._jobs.values())
        if not jobs:
            return None
        running = [j for j in jobs if j.status in (JobStatus.RUNNING, JobStatus.PENDING)]
        pool = running or jobs
        return max(pool, key=lambda j: j.created_at)


# 싱글톤
job_manager = JobManager()
