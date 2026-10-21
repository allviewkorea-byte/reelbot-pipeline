"""쇼츠 hero(형식 A) API — 프론트 /shorts/hero. 테스트는 미리보기만(유튜브 업로드 없음)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services import shorts_hero, shorts_songs

router = APIRouter()


class HeroTestReq(BaseModel):
    channel: str = "workout_music"
    concept: str = "bat_break"


class ChannelReq(BaseModel):
    channel: str = "workout_music"


@router.get("")
def hero_home(channel: str = "workout_music"):
    """hero 준비 상태 · 콘셉트 · 최근 실행(미리보기·비용·관련 동영상 링크) · 곡 분석 · 앤섬 상태."""
    analysis = sorted(shorts_songs.read_analysis(channel).values(),
                      key=lambda a: a.get("analyzed_at") or "", reverse=True)
    return {
        "hero": shorts_hero.hero_status(channel),
        "concepts": [{"id": k, "label": v["label"], "seconds": v["seconds"]} for k, v in shorts_hero.CONCEPTS.items()],
        "runs": shorts_hero.read_runs(channel)[:10],
        "run_state": shorts_hero.state(),
        "songs": analysis[:10],
        "anthem": shorts_hero.anthem_state(),
        "cap_usd": shorts_hero.cost_cap(),
    }


@router.post("/test")
def hero_test(req: HeroTestReq, background: BackgroundTasks):
    """형식 A 테스트 1편(미리보기 두 버전). hero 미확정·진행 중·음악 작업 중이면 거절."""
    from services import shorts_produce
    if req.concept not in shorts_hero.CONCEPTS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 콘셉트: {req.concept}")
    st = shorts_hero.hero_status(req.channel)
    if not st["ready"]:
        raise HTTPException(status_code=400, detail=st["reason"])
    if shorts_hero.is_running() or shorts_produce.is_running():
        raise HTTPException(status_code=409, detail="쇼츠 제작이 이미 진행 중이에요.")
    if shorts_produce.music_busy():
        raise HTTPException(status_code=409, detail="음악 제작이 진행 중이에요 — 끝난 뒤 다시 시도해 주세요.")
    background.add_task(shorts_hero.run_background, req.concept, req.channel)
    return {"status": "running", "concept": req.concept}


@router.post("/songs/analyze")
def songs_analyze(req: ChannelReq, background: BackgroundTasks):
    """업로드된 플리 영상 속 우리 곡 상위 3개 — 후렴·드롭·BPM 분석(백그라운드, 결과는 GET 에 표시)."""
    background.add_task(shorts_songs.analyze_top, req.channel, n=3)
    return {"status": "running"}


@router.post("/anthem")
def anthem(req: ChannelReq, background: BackgroundTasks):
    """쿵쿵따 스타디움 운동 앤섬(연주곡) Suno 1회 = 2클립 → 운동 채널 라이브러리."""
    if shorts_hero.anthem_state().get("status") == "running":
        raise HTTPException(status_code=409, detail="앤섬 생성이 이미 진행 중이에요.")
    background.add_task(_anthem_safe, req.channel)
    return {"status": "running"}


def _anthem_safe(channel: str) -> None:
    try:
        shorts_hero.make_anthem(channel)
    except Exception:  # noqa: BLE001 - 상태(_ANTHEM)에 실패가 기록됨
        pass
