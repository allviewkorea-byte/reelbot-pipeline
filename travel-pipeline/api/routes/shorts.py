"""쇼츠 — 사람 캐스트 시트 API (프론트 /shorts/cast). 백곰 /sayeon/cast* 와 분리."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from services import shorts_cast, shorts_cast_upload, shorts_produce, shorts_series

router = APIRouter()


class CastTarget(BaseModel):
    channel: str = "workout_music"
    role: str = "lead"


class CastAspectReq(CastTarget):
    aspect: str


class CastApproveReq(CastTarget):
    approved: bool


class CastSlotReq(CastTarget):
    aspect: str
    cols: int | None = None
    crop: bool | None = None
    labels: list[str] | None = None


def _check(channel: str, role: str) -> dict:
    entry = shorts_cast.get_entry(channel, role)
    if not entry:
        raise HTTPException(status_code=404, detail=f"알 수 없는 캐스트입니다: {channel}/{role}")
    return entry


def _check_generate(channel: str, role: str) -> None:
    if _check(channel, role).get("source", "generate") != "generate":
        raise HTTPException(status_code=400, detail="업로드 캐스트는 자동 생성하지 않습니다 — 이미지를 올려 주세요.")


@router.get("/cast")
def cast(channel: str = "workout_music"):
    """채널 사람 캐스트 + 아스펙트 URL + 확정 상태 + 아스펙트 순서·라벨."""
    if channel not in shorts_cast.channels():
        raise HTTPException(status_code=404, detail=f"사람 캐스트가 없는 채널입니다: {channel}")
    return {
        "channel": channel,
        "cast": shorts_cast.list_cast(channel),
        "aspects": [{"key": k, "label": shorts_cast.ASPECT_LABELS[k]} for k in shorts_cast.ASPECT_KEYS],
        "anchor": shorts_cast.ANCHOR,
        "roles": shorts_cast_upload.list_roles(channel),
    }


@router.post("/cast/generate")
def cast_generate(req: CastTarget, background: BackgroundTasks):
    """전체(8장) 생성을 백그라운드로 시작. 진행은 GET /shorts/cast/status 폴링."""
    _check_generate(req.channel, req.role)
    if shorts_cast.is_running(req.channel, req.role):
        raise HTTPException(status_code=409, detail="이미 생성 중입니다.")
    background.add_task(shorts_cast.run_generation, req.channel, req.role)
    return {"channel": req.channel, "role": req.role, "status": "running"}


@router.get("/cast/status")
def cast_status(channel: str = "workout_music", role: str = "lead"):
    return shorts_cast.get_progress(channel, role)


@router.post("/cast/aspect")
def cast_aspect(req: CastAspectReq):
    """아스펙트 1장 재생성(동기). 확정은 풀린다."""
    _check_generate(req.channel, req.role)
    if req.aspect not in shorts_cast.ASPECT_KEYS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 아스펙트입니다: {req.aspect}")
    if shorts_cast.is_running(req.channel, req.role):
        raise HTTPException(status_code=409, detail="전체 생성 중에는 1장 재생성을 할 수 없습니다.")
    try:
        return shorts_cast.regenerate_aspect(req.channel, req.role, req.aspect)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/cast/approve")
def cast_approve(req: CastApproveReq):
    """확정/해제(role 단위) — R2 cast/{channel}/state.json. 확정본만 영상 레퍼런스로 쓴다.

    업로드 role 은 필수 슬롯이 모두 있어야 확정된다."""
    entry = _check(req.channel, req.role)
    try:
        if entry.get("source") == "upload":
            return shorts_cast_upload.approve(req.channel, req.role, req.approved)
        return shorts_cast.set_status(req.channel, req.role, "approved" if req.approved else "draft")
    except shorts_cast_upload.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/cast/upload")
async def cast_upload(
    file: UploadFile = File(...),
    role: str = Form(...),
    aspect: str = Form(...),
    channel: str = Form("workout_music"),
    cols: int | None = Form(None),
):
    """슬롯 이미지 업로드(png/jpg/webp → PNG) + 시트면 칸 자르기. 그 role 의 확정은 풀린다."""
    _check(channel, role)
    data = await file.read()
    try:
        return shorts_cast_upload.save_upload(channel, role, aspect, data, file.filename or "", cols)
    except shorts_cast_upload.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/cast/slot")
def cast_slot(req: CastSlotReq):
    """시트 칸 수(4/5) 변경·자르지 않기 토글·칸별 라벨 지정."""
    _check(req.channel, req.role)
    try:
        return shorts_cast_upload.update_slot(req.channel, req.role, req.aspect,
                                              cols=req.cols, crop=req.crop, labels=req.labels)
    except shorts_cast_upload.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── 시즌 1 시리즈·테스트 제작 ────────────────────────────────────────────
class TestRunReq(BaseModel):
    channel: str = "workout_music"
    days: list[int] = [1, 4, 6]
    compare_seedance: bool = True
    upload: bool = False  # 테스트 기본: 유튜브에 올리지 않고 릴봇 화면(R2 미리보기)에서만 확인


@router.get("/series")
def series(channel: str = "workout_music"):
    """series.json(없으면 초기 계획) + 진행 상태 + 미확정 캐스트."""
    return {"series": shorts_series.load(channel), "run": shorts_produce.run_state(),
            "unapproved": shorts_produce.unapproved_roles(channel)}


@router.post("/test-run")
def test_run(req: TestRunReq, background: BackgroundTasks):
    """테스트 제작(최대 3편) + Seedance 비교 1회. 5인 캐스트가 모두 확정돼야 시작.
    upload=False(기본)면 R2 미리보기만 — 유튜브에는 올리지 않는다."""
    missing = shorts_produce.unapproved_roles(req.channel)
    if missing:
        raise HTTPException(status_code=400, detail="확정되지 않은 캐스트가 있어요: " + ", ".join(missing))
    if not req.days or len(req.days) > 3 or any(d < 1 or d > 15 for d in req.days):
        raise HTTPException(status_code=400, detail="테스트는 Day 1~15 중 최대 3편까지예요.")
    if shorts_produce.is_running():
        raise HTTPException(status_code=409, detail="쇼츠 제작이 이미 진행 중이에요.")
    if shorts_produce.music_busy():
        raise HTTPException(status_code=409, detail="음악 제작이 진행 중이에요 — 끝난 뒤 다시 시도해 주세요.")
    background.add_task(shorts_produce.run_test, req.days, channel=req.channel,
                        compare_seedance=req.compare_seedance, upload=req.upload)
    return {"status": "running", "days": req.days, "upload": req.upload}
