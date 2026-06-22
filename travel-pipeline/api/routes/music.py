"""음악(Rooftop Music) 라우터 — sunoapi.org 콜백 수신(보조).

완료 감지는 폴링이 1차(R2 저장 책임). 이 콜백은 보조 채널이다:
  - callBackUrl 은 suno 요청의 필드라 엔드포인트를 최소로 제공한다.
  - callbackType == complete 일 때만 멱등 R2 저장을 트리거(이미 저장됐으면 skip).
  - theme_slug 는 콜백 본문에 없으므로 callBackUrl 쿼리(?theme_slug=)로 전달받는다.

MUSIC_CALLBACK_BASE_URL 미설정이면 suno 가 콜백을 보내지 않으며, 폴링만으로
정상 동작한다(이 라우트는 호출되지 않을 뿐 문제 없음).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from services import music_suno

logger = logging.getLogger(__name__)

router = APIRouter()


def _authorized_cron(authorization: str | None) -> bool:
    """크론 인증 — Authorization: Bearer ${CRON_SECRET}. 미설정 시 무조건 거부(안전 기본값)."""
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        return False
    return authorization == f"Bearer {secret}"


def _run_produce() -> None:
    """백그라운드: 주제 자동 생성 → 음원 → 영상 → 검토 대기 큐 적재(run_theme)."""
    try:
        from services import music_produce
        result = music_produce.run_theme(video=True, upload=False)
        slug = (result.get("theme") or {}).get("slug")
        vid = (result.get("video") or {}).get("video_id")
        logger.info("[music-produce] 완료 slug=%s video_id=%s", slug, vid)
    except Exception as e:  # noqa: BLE001 - 백그라운드 실패는 로깅만(큐는 비어 있게 둠)
        logger.warning("[music-produce] 백그라운드 실패: %s", e)


@router.post("/produce")
def produce(background: BackgroundTasks, authorization: str | None = Header(default=None)):
    """cron 트리거 — 주제→음원→영상→큐 적재를 비동기로 시작하고 즉시 반환.

    10분+ 작업이라 fire-and-forget(BackgroundTasks)으로 타임아웃을 피한다.
    CRON_SECRET 헤더 필수(백곰 cron 패턴 동일).
    """
    if not _authorized_cron(authorization):
        raise HTTPException(status_code=401, detail="unauthorized")
    background.add_task(_run_produce)
    return {"ok": True, "status": "started"}


def _run_trend_analysis() -> None:
    """백그라운드: 유튜브 인기 음악 분석 → music_trends 저장."""
    try:
        from services import music_trend
        insight = music_trend.run_analysis()
        logger.info("[music-trend] 분석 완료 무드=%s", insight.get("mood_keywords"))
    except Exception as e:  # noqa: BLE001 - 백그라운드 실패는 로깅만
        logger.warning("[music-trend] 분석 실패: %s", e)


@router.post("/trends/analyze")
def trends_analyze(background: BackgroundTasks, authorization: str | None = Header(default=None)):
    """cron 트리거 — 트렌드 분석을 비동기로 시작하고 즉시 반환(주 2회).

    유튜브 검색 + GPT 라 수십 초~분 → fire-and-forget. CRON_SECRET 헤더 필수.
    """
    if not _authorized_cron(authorization):
        raise HTTPException(status_code=401, detail="unauthorized")
    background.add_task(_run_trend_analysis)
    return {"ok": True, "status": "started"}


class TestRenderBody(BaseModel):
    mood: str | None = None  # citypop/cafe/ballad/workout/sleep (없으면 기본 citypop)


@router.post("/test-render")
def test_render(body: TestRenderBody | None = None):
    """대시보드 '테스트 영상 생성' — 즉석 10초 영상 렌더(유튜브 X, 큐 저장 X).

    동기 호출(완료 시 mp4 URL 반환). CRON 인증 불필요(대시보드 직접 호출).
    Remotion(USE_REMOTION on) 우선, 실패/off 면 ffmpeg 폴백.
    """
    from services import music_test
    mood = body.mood if body else None
    try:
        result = music_test.render_test(mood=mood)
    except Exception as e:  # noqa: BLE001 - 실패 원인을 프론트로 전달
        logger.warning("[music-test] 렌더 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"테스트 렌더 실패: {e}") from e
    return {"ok": True, **result}


@router.post("/manual-render")
def manual_render(background: BackgroundTasks, body: TestRenderBody | None = None):
    """수동 영상 생성(#26) — 진짜 음원 1곡 → 풀 렌더 → 검토 큐 적재(비동기). 유튜브 X.

    수 분~수십 분 걸려 BackgroundTasks 로 시작하고 job_id 즉시 반환. 동시 1개 제한.
    완료 시 music_uploads 에 status=pending 으로 저장(검토 큐 일반 카드). 상태는
    GET /manual-render/status/{job_id} 폴링.
    """
    from services import music_manual
    started = music_manual.start(mood=body.mood if body else None)
    if not started.get("ok"):
        raise HTTPException(status_code=409, detail=started.get("error") or "이미 진행 중")
    background.add_task(music_manual.run, started["job_id"])
    return {"ok": True, "job_id": started["job_id"]}


@router.get("/manual-render/status/{job_id}")
def manual_render_status(job_id: str):
    """수동 생성 진행 상태 폴링 — {status, step, video_url, mix_id, error}. 없으면 404."""
    from services import music_manual
    st = music_manual.get_status(job_id)
    if st is None:
        raise HTTPException(status_code=404, detail="해당 job 을 찾을 수 없습니다(재시작 시 소실).")
    return st


@router.get("/trends")
def trends_latest():
    """최신 트렌드 인사이트(대시보드/가이드 표시용). 없으면 trend=None."""
    from services import music_trend
    return {"trend": music_trend.get_latest()}


@router.post("/suno-callback")
async def suno_callback(request: Request, theme_slug: str = ""):
    """suno 생성 콜백. complete 면 멱등 R2 저장을 트리거한다."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - 비정상 본문도 200 으로 흡수(재전송 폭주 방지)
        logger.warning("[music-callback] JSON 파싱 실패")
        return {"ok": False, "error": "invalid json"}

    data = body.get("data") or {}
    cb_type = data.get("callbackType") or body.get("callbackType") or ""
    task_id = data.get("task_id") or data.get("taskId") or ""
    logger.info(
        "[music-callback] type=%s task=%s theme=%s", cb_type, task_id, theme_slug
    )

    if cb_type != "complete":
        # text / first 등 중간 콜백은 로그만(R2 저장은 complete 에서).
        return {"ok": True, "ignored": cb_type}

    # complete 본문의 곡 배열(키 명이 docs/실응답에 따라 다를 수 있어 관대하게 탐색).
    tracks = data.get("data") or data.get("sunoData") or []
    if not isinstance(tracks, list) or not tracks:
        logger.warning("[music-callback] complete 인데 트랙 배열 없음")
        return {"ok": True, "stored": 0}

    try:
        records = music_suno.store_tracks(theme_slug or "untitled", task_id, tracks)
        return {"ok": True, "stored": len(records)}
    except Exception as e:  # noqa: BLE001 - 콜백 실패해도 폴링이 1차라 200 으로 흡수
        logger.warning("[music-callback] 저장 실패: %s", e)
        return {"ok": False, "error": str(e)}
