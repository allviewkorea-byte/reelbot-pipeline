"""작업 진행 상황 폴링 라우터."""

from fastapi import APIRouter, HTTPException

from api.jobs import job_manager
from api.schemas import JobStatusResponse

router = APIRouter()


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status.value,
        progress=job.progress,
        current_step=job.current_step,
        result=job.result,
        error=job.error,
    )


@router.get("/jobs/active")
def active_job():
    """현재 진행 중(없으면 가장 최근) job 1건 — 대시보드 노드그래프 점등용(읽기 전용).

    유휴(아무 job 없음)면 None 반환. 기존 job 생성·진행 로직은 건드리지 않는다.
    """
    job = job_manager.active_job()
    if job is None:
        return None
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": job.progress,
        "current_step": job.current_step,
        "created_at": job.created_at.isoformat(),
    }
