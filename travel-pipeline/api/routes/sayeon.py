"""사연(이미지 기반) 트랙 라우터.

- POST /sayeon/split             사연 대본 → 씬 리스트(JSON) (PR-S1, 동기)
- POST /sayeon/character-sheet   캐릭터 시트 생성·R2 저장 (PR-S2a)
- POST /sayeon/scenes            시트 reference 로 씬 이미지 생성 (PR-S2b)

진행 상황은 기존 GET /jobs/{job_id}/status 로 폴링한다(공용 job_manager 사용).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.jobs import job_manager
from api.schemas import (
    SayeonJobResponse,
    SayeonScenesRequest,
    SayeonSheetRequest,
    SayeonSplitRequest,
    SayeonSplitResponse,
)
from services.sayeon_character import generate_character_sheet
from services.sayeon_scene import generate_scenes
from services.sayeon_split import split_script

router = APIRouter()


@router.post("/split", response_model=SayeonSplitResponse)
def split(req: SayeonSplitRequest):
    """국문 사연 대본을 씬 리스트(JSON)로 분할한다. gpt-4o-mini 1회, 동기 응답."""
    try:
        return split_script(
            req.script,
            num_scenes=req.num_scenes,
            character_anchor=req.character_anchor or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _run_sheet(job_id: str, channel_id: str, character: dict, sheet_model: str | None) -> None:
    job_manager.start_job(job_id)
    try:
        def cb(pct: int, msg: str) -> None:
            job_manager.update_progress(job_id, pct, msg)

        result = generate_character_sheet(
            channel_id,
            character,
            sheet_model=sheet_model,
            output_dir=f"output/sayeon/characters/{channel_id}",
            progress_cb=cb,
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


@router.post("/character-sheet", response_model=SayeonJobResponse)
def character_sheet(req: SayeonSheetRequest, background: BackgroundTasks):
    """채널/캐릭터 설정으로 웹툰 캐릭터 시트를 1회 생성하고 R2에 저장한다."""
    job = job_manager.create_job("sayeon_sheet")
    background.add_task(
        _run_sheet,
        job.job_id,
        req.channel_id,
        req.character.model_dump(),
        req.sheet_model,
    )
    return SayeonJobResponse(job_id=job.job_id, status=job.status.value)


def _run_scenes(
    job_id: str,
    sheet_url: str,
    scenes: list[dict],
    anchor: str,
    num_images: int,
    seed: int,
) -> None:
    job_manager.start_job(job_id)
    try:
        def cb(pct: int, msg: str) -> None:
            job_manager.update_progress(job_id, pct, msg)

        result = generate_scenes(
            job_id,
            sheet_url,
            scenes,
            anchor=anchor,
            num_images=num_images,
            seed=seed,
            progress_cb=cb,
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


@router.post("/scenes", response_model=SayeonJobResponse)
def scenes(req: SayeonScenesRequest, background: BackgroundTasks):
    """저장된 캐릭터 시트를 reference 로 씬 이미지를 생성한다(씬당 num_images 후보)."""
    job = job_manager.create_job("sayeon_scenes")
    background.add_task(
        _run_scenes,
        job.job_id,
        req.sheet_url,
        req.scenes,
        req.anchor,
        req.num_images,
        req.seed,
    )
    return SayeonJobResponse(job_id=job.job_id, status=job.status.value)
