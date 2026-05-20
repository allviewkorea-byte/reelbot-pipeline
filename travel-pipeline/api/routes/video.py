"""콘티 승인 후 영상 생성 라우터."""

from fastapi import APIRouter, BackgroundTasks

from api.jobs import job_manager
from api.schemas import StoryboardGenerateResponse, VideoStartRequest

router = APIRouter()


def _run_video(
    job_id: str,
    scenes: list[dict],
    approved_storyboards: list[dict],
    scenario_mode: str,
    seedance_mode: str,
):
    from main import generate_video_from_storyboard

    job_manager.start_job(job_id)
    try:
        def cb(progress: int, step: str):
            job_manager.update_progress(job_id, progress, step)

        result = generate_video_from_storyboard(
            scenes=scenes,
            approved_storyboards=approved_storyboards,
            output_dir=f"output/video/{job_id}",
            scenario_mode=scenario_mode,
            seedance_mode=seedance_mode,
            progress_callback=cb,
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:
        job_manager.fail_job(job_id, str(e))


@router.post("/start", response_model=StoryboardGenerateResponse)
def start(req: VideoStartRequest, background: BackgroundTasks):
    job = job_manager.create_job("video")
    background.add_task(
        _run_video,
        job.job_id,
        req.scenes,
        req.approved_storyboards,
        req.scenario_mode,
        req.seedance_mode,
    )
    return StoryboardGenerateResponse(job_id=job.job_id, status=job.status.value)
