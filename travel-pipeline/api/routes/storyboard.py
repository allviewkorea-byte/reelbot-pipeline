"""콘티 생성 / 재생성 라우터."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks

from api.jobs import job_manager
from api.schemas import (
    ScenarioGenerateRequest,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
    StoryboardRegenerateRequest,
)
from storyboard import generate_storyboard, regenerate_single_scene

router = APIRouter()


@router.post("/scenario")
def scenario(req: ScenarioGenerateRequest):
    """시나리오 + 씬 리스트 생성 (동기). 콘티 생성 전 단계."""
    from main import generate_scenario

    return generate_scenario(req.country, req.duration_min)


def _run_storyboard(
    job_id: str,
    scenes: list[dict],
    character_image_path: str | None,
    model: str = "default",
):
    job_manager.start_job(job_id)
    try:
        def cb(idx: int, total: int, msg: str):
            job_manager.update_progress(job_id, int(idx / max(total, 1) * 100), msg)

        results = generate_storyboard(
            scenes=scenes,
            character_image_path=character_image_path or "",
            output_dir=f"output/storyboard/{job_id}",
            progress_callback=cb,
            model=model,
        )
        job_manager.complete_job(job_id, {"storyboards": results})
    except Exception as e:
        job_manager.fail_job(job_id, str(e))


@router.post("/generate", response_model=StoryboardGenerateResponse)
def generate(req: StoryboardGenerateRequest, background: BackgroundTasks):
    job = job_manager.create_job("storyboard")
    background.add_task(
        _run_storyboard,
        job.job_id,
        req.scenes,
        req.character_image_path,
        req.storyboard_model,
    )
    return StoryboardGenerateResponse(job_id=job.job_id, status=job.status.value)


def _run_regenerate(
    job_id: str,
    scene: dict,
    scene_id: int,
    character_image_path: str | None,
    extra_instructions: str | None,
    model: str = "default",
):
    job_manager.start_job(job_id)
    try:
        output_path = f"output/storyboard/{job_id}/scene_{scene_id}.png"
        result = regenerate_single_scene(
            scene=scene,
            character_image_path=character_image_path or "",
            output_path=output_path,
            extra_instructions=extra_instructions,
            model=model,
        )
        job_manager.complete_job(job_id, {"storyboard": result})
    except Exception as e:
        job_manager.fail_job(job_id, str(e))


@router.post("/regenerate", response_model=StoryboardGenerateResponse)
def regenerate(req: StoryboardRegenerateRequest, background: BackgroundTasks):
    """특정 씬만 재생성. 기존 storyboard job_id 폴더에 덮어쓴다."""
    job = job_manager.create_job("storyboard")
    background.add_task(
        _run_regenerate,
        req.job_id,
        req.scene,
        req.scene_id,
        req.character_image_path,
        req.extra_instructions,
        req.storyboard_model,
    )
    return StoryboardGenerateResponse(job_id=job.job_id, status=job.status.value)
