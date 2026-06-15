"""사연(이미지 기반) 트랙 라우터.

- POST /sayeon/generate-script   랜덤 감성 사연 자동 작성 (동기)
- POST /sayeon/split             사연 대본 → 씬 리스트(JSON) (PR-S1, 동기)
- POST /sayeon/character-sheet   캐릭터 시트 생성·R2 저장 (PR-S2a)
- POST /sayeon/scenes            시트 reference 로 씬 이미지 생성 (PR-S2b)
- POST /sayeon/tts               씬 narration → TTS 음성 + 타이밍 맵 (PR-S3)
- POST /sayeon/assemble          씬+타이밍+자막+음성 → 완성 mp4 (PR-S4)
- POST /sayeon/thumbnail         씬 이미지 + 후킹 → 썸네일 PNG (PR-S5, 동기)
- POST /sayeon/generate          사연 글 → 완성 영상 + 썸네일 (end-to-end, 백그라운드)

진행 상황은 기존 GET /jobs/{job_id}/status 로 폴링한다(공용 job_manager 사용).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.jobs import job_manager
from api.schemas import (
    SayeonAssembleRequest,
    SayeonAutoScriptRequest,
    SayeonAutoScriptResponse,
    SayeonGenerateRequest,
    SayeonJobResponse,
    SayeonScenesRequest,
    SayeonSheetRequest,
    SayeonSplitRequest,
    SayeonSplitResponse,
    SayeonThumbnailRequest,
    SayeonThumbnailResponse,
    SayeonTtsRequest,
)
from services.sayeon_assemble import generate_assemble
from services.sayeon_autoscript import generate_script as generate_auto_script
from services.sayeon_character import generate_character_sheet
from services.sayeon_orchestrate import generate_full
from services.sayeon_scene import generate_scenes
from services.sayeon_split import split_script
from services.sayeon_thumbnail import generate_thumbnail
from services.sayeon_tts import generate_tts

router = APIRouter()


@router.post("/generate-script", response_model=SayeonAutoScriptResponse)
def generate_script(req: SayeonAutoScriptRequest):
    """랜덤(또는 지정) 주제로 1인칭 감성 사연을 자동 작성한다. gpt-4o-mini, 동기."""
    try:
        return generate_auto_script(
            topic=req.topic or "",
            character=req.character.model_dump() if req.character else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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


@router.post("/thumbnail", response_model=SayeonThumbnailResponse)
def thumbnail(req: SayeonThumbnailRequest):
    """씬 이미지 + 후킹 문구로 썸네일 PNG 를 만든다. ffmpeg 1프레임, 동기 응답."""
    try:
        return generate_thumbnail(
            req.image_url,
            hook_text=req.hook_text or "",
            highlight=req.highlight or "",
            script=req.script or "",
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


def _run_tts(
    job_id: str, scenes: list[dict], voice_id: str | None, gap_sec: float
) -> None:
    job_manager.start_job(job_id)
    try:
        def cb(pct: int, msg: str) -> None:
            job_manager.update_progress(job_id, pct, msg)

        result = generate_tts(
            job_id, scenes, voice_id=voice_id, gap_sec=gap_sec, progress_cb=cb
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


def _run_assemble(
    job_id: str, scenes: list[dict], scene_timings: list[dict], audio_url: str
) -> None:
    job_manager.start_job(job_id)
    try:
        def cb(pct: int, msg: str) -> None:
            job_manager.update_progress(job_id, pct, msg)

        result = generate_assemble(
            job_id, scenes, scene_timings, audio_url, progress_cb=cb
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


@router.post("/tts", response_model=SayeonJobResponse)
def tts(req: SayeonTtsRequest, background: BackgroundTasks):
    """씬 narration 을 라인별 TTS 로 생성하고 합친 오디오 + 씬 타이밍 맵을 만든다."""
    job = job_manager.create_job("sayeon_tts")
    background.add_task(_run_tts, job.job_id, req.scenes, req.voice_id, req.gap_sec)
    return SayeonJobResponse(job_id=job.job_id, status=job.status.value)


@router.post("/assemble", response_model=SayeonJobResponse)
def assemble(req: SayeonAssembleRequest, background: BackgroundTasks):
    """씬 이미지 + 타이밍 + 자막 + 음성을 켄번즈·크로스페이드로 합성해 mp4 를 만든다."""
    job = job_manager.create_job("sayeon_assemble")
    background.add_task(
        _run_assemble, job.job_id, req.scenes, req.scene_timings, req.audio_url
    )
    return SayeonJobResponse(job_id=job.job_id, status=job.status.value)


def _run_generate(job_id: str, req: SayeonGenerateRequest) -> None:
    job_manager.start_job(job_id)
    try:
        def cb(pct: int, msg: str) -> None:
            job_manager.update_progress(job_id, pct, msg)

        result = generate_full(
            job_id,
            req.script,
            character_spec=req.character_spec.model_dump() if req.character_spec else None,
            sheet_url=req.sheet_url or "",
            anchor=req.anchor or "",
            voice_id=req.voice_id,
            num_scenes=req.num_scenes,
            gap_sec=req.gap_sec,
            thumbnail_scene_index=req.thumbnail_scene_index,
            privacy=req.privacy,
            progress_cb=cb,
        )
        job_manager.complete_job(job_id, result)
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


@router.post("/generate", response_model=SayeonJobResponse)
def generate(req: SayeonGenerateRequest, background: BackgroundTasks):
    """사연 글 → 완성 영상 + 썸네일. 6개 서비스를 순서대로 체인하는 end-to-end job."""
    job = job_manager.create_job("sayeon_generate")
    background.add_task(_run_generate, job.job_id, req)
    return SayeonJobResponse(job_id=job.job_id, status=job.status.value)
