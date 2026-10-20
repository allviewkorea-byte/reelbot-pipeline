"""쇼츠 — 사람 캐스트 시트 API (프론트 /shorts/cast). 백곰 /sayeon/cast* 와 분리."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services import shorts_cast

router = APIRouter()


class CastTarget(BaseModel):
    channel: str = "workout_music"
    role: str = "lead"


class CastAspectReq(CastTarget):
    aspect: str


class CastApproveReq(CastTarget):
    approved: bool


def _check(channel: str, role: str) -> None:
    if not shorts_cast.get_entry(channel, role):
        raise HTTPException(status_code=404, detail=f"알 수 없는 캐스트입니다: {channel}/{role}")


@router.get("/cast")
def cast(channel: str = "workout_music"):
    """채널 사람 캐스트 + 아스펙트 URL + 확정 상태 + 아스펙트 순서·라벨."""
    if channel not in shorts_cast.channels():
        raise HTTPException(status_code=404, detail=f"사람 캐스트가 없는 채널입니다: {channel}")
    return {
        "channel": channel,
        "cast": shorts_cast.list_cast(channel),
        "aspects": [{"key": k, "label": shorts_cast.ASPECT_LABELS[k]} for k in shorts_cast.ASPECT_KEYS],
    }


@router.post("/cast/generate")
def cast_generate(req: CastTarget, background: BackgroundTasks):
    """전체(8장) 생성을 백그라운드로 시작. 진행은 GET /shorts/cast/status 폴링."""
    _check(req.channel, req.role)
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
    _check(req.channel, req.role)
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
    """확정/해제 — R2 cast/{channel}/state.json. 확정본만 영상 레퍼런스로 쓴다."""
    _check(req.channel, req.role)
    try:
        return shorts_cast.set_status(req.channel, req.role, "approved" if req.approved else "draft")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
