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
