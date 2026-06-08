"""사연(이미지 기반) 트랙 라우터.

- POST /sayeon/character-sheet   캐릭터 시트 생성·R2 저장 (PR-S2a)

진행 상황은 기존 GET /jobs/{job_id}/status 로 폴링한다(공용 job_manager 사용).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from api.jobs import job_manager
from api.schemas import SayeonJobResponse, SayeonSheetRequest
from services.sayeon_character import generate_character_sheet

router = APIRouter()


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
