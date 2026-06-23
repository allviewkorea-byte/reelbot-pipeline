"""음악(Rooftop Music) 라우터 — sunoapi.org 콜백 수신(보조).

완료 감지는 폴링이 1차(R2 저장 책임). 이 콜백은 보조 채널이다:
  - callBackUrl 은 suno 요청의 필드라 엔드포인트를 최소로 제공한다.
  - callbackType == complete 일 때만 멱등 R2 저장을 트리거(이미 저장됐으면 skip).
  - theme_slug 는 콜백 본문에 없으므로 callBackUrl 쿼리(?theme_slug=)로 전달받는다.

MUSIC_CALLBACK_BASE_URL 미설정이면 suno 가 콜백을 보내지 않으며, 폴링만으로
정상 동작한다(이 라우트는 호출되지 않을 뿐 문제 없음).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import BaseModel

from services import music_suno

logger = logging.getLogger(__name__)

# #28 cron 중복 생성 방지 — 8/9/10시 3개 cron 중 '오늘 첫 호출'만 생성, 나머지 스킵.
# #28-A: 첫 호출이 0~120분 랜덤 지연 후 생성(봇 패턴 회피). 선점은 지연 시작 전에 잡는다.
_PRODUCE_LOCK = threading.Lock()
_produced_date: str | None = None  # 'YYYY-MM-DD'(KST) — 이 프로세스가 오늘 생성을 선점
_produced_at: datetime | None = None  # 선점 시각(UTC) — 인스턴스 재시작/멈춤 대비 stale 무효화
_PREEMPT_TTL = 3 * 3600  # 선점 유효시간(초). 초과 시 무효화(그날 영상 누락 방지)
_MAX_DELAY = 7200  # 최대 지연(초) = 120분
_KST = timezone(timedelta(hours=9))

router = APIRouter()


def _authorized_cron(authorization: str | None) -> bool:
    """크론 인증 — Authorization: Bearer ${CRON_SECRET}. 미설정 시 무조건 거부(안전 기본값)."""
    secret = (os.getenv("CRON_SECRET") or "").strip()
    if not secret:
        return False
    return authorization == f"Bearer {secret}"


def _release_preempt() -> None:
    global _produced_date, _produced_at
    with _PRODUCE_LOCK:
        _produced_date = None
        _produced_at = None


def _produce_step_for(msg: str) -> str | None:
    """produce/run_theme 진행 메시지 → 표준 단계(music_jobs.STEPS) 매핑(파이프라인 시각화)."""
    if "가사" in msg:
        return "lyrics"
    if "영상" in msg:
        return "video"
    if "유튜브" in msg or "업로드" in msg:
        return "upload"
    if "마스터" in msg or "믹스" in msg:
        return "mix"
    if "보컬" in msg or "연주" in msg or "음원" in msg:
        return "vocal"
    return None


def _run_produce() -> None:
    """백그라운드: 주제 자동 생성 → 음원 → 영상 → 검토 대기 큐 적재(run_theme).

    #36 운영 가시성 — music_jobs 로 단계 진행을 DB 기록(대시보드 파이프라인 시각화).
    추적은 best-effort 라 실패해도 제작 흐름·비용에 영향 없음.
    """
    from services import music_jobs
    job_id = music_jobs.start_job("cron")
    try:
        from services import music_channel, music_produce
        n = music_channel.get_track_count()  # 대시보드 곡수(기본 1) — 비용 직접 제어(#30)
        logger.info("[music-produce] 곡수=%d 로 생성 시작", n)
        music_jobs.update_job_step(job_id, "theme")

        def _progress(msg: str) -> None:
            step = _produce_step_for(msg)
            if step:
                try:
                    music_jobs.update_job_step(job_id, step)
                except Exception:  # noqa: BLE001
                    pass

        result = music_produce.run_theme(video=True, upload=False, n=n, progress=_progress)
        slug = (result.get("theme") or {}).get("slug")
        vid = (result.get("video") or {}).get("video_id")
        try:
            music_jobs.complete_job(job_id, mix_id=vid)
        except Exception:  # noqa: BLE001
            pass
        logger.info("[music-produce] 완료 slug=%s video_id=%s", slug, vid)
    except Exception as e:  # noqa: BLE001 - 백그라운드 실패는 로깅만(큐는 비어 있게 둠)
        try:
            music_jobs.fail_job(job_id, str(e))
        except Exception:  # noqa: BLE001
            pass
        # 실패 시 오늘 선점 해제 → 다음 cron(9/10시)이 재시도하도록.
        _release_preempt()
        logger.warning("[music-produce] 백그라운드 실패(선점 해제, 재시도 허용): %s", e)


async def _produce_with_delay(delay_seconds: int) -> None:
    """랜덤 지연(asyncio.sleep, 이벤트루프 안 막음) 후 생성(블로킹은 to_thread)."""
    logger.info("[music-produce] %d초(%d분) 지연 후 생성 예약", delay_seconds, delay_seconds // 60)
    try:
        await asyncio.sleep(delay_seconds)
    except Exception:  # noqa: BLE001 - 취소 등은 무시하고 진행 시도
        pass
    # _run_produce 는 자체적으로 성공 시 선점 유지 / 실패 시 선점 해제한다.
    await asyncio.to_thread(_run_produce)


@router.post("/produce")
def produce(background: BackgroundTasks, authorization: str | None = Header(default=None)):
    """cron 트리거 — 0~120분 랜덤 지연 후 영상 생성을 예약하고 즉시 반환.

    #28: 8/9/10시 3개 cron → '오늘 첫 호출'만 생성, 나머지 스킵(프로세스 선점 + DB 이중 확인).
    #28-A: 첫 호출은 0~120분 랜덤 지연 후 생성(봇 패턴 회피). 선점은 지연 시작 전에 잡으므로
    지연 중 들어온 다른 cron 은 즉시 skip. 선점이 3시간 넘으면 무효화(재시작/멈춤 대비).
    CRON_SECRET 필수.
    """
    if not _authorized_cron(authorization):
        raise HTTPException(status_code=401, detail="unauthorized")

    global _produced_date, _produced_at
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    now_utc = datetime.now(timezone.utc)
    with _PRODUCE_LOCK:
        # 선점이 오래됐으면(인스턴스 재시작으로 지연 작업 유실 등) 무효화 → 재시도 허용.
        if (
            _produced_date == today and _produced_at is not None
            and (now_utc - _produced_at).total_seconds() > _PREEMPT_TTL
        ):
            _produced_date = None
            _produced_at = None
        if _produced_date == today:
            return {"ok": True, "skipped": True, "reason": "이미 오늘 영상 생성됨(프로세스 선점)"}
        from services import music_uploads
        if music_uploads.count_today_kst() > 0:
            _produced_date = today
            _produced_at = now_utc
            return {"ok": True, "skipped": True, "reason": "이미 오늘 영상 생성됨"}
        # 선점 — 동시 호출(8/9시 동시 도착)이라도 두 번째는 위 가드로 스킵.
        _produced_date = today
        _produced_at = now_utc
        delay = random.randint(0, _MAX_DELAY)
        background.add_task(_produce_with_delay, delay)
    return {
        "ok": True,
        "status": "scheduled",
        "delay_seconds": delay,
        "estimated_start_minutes": delay // 60,
    }


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
    track_count: int | None = None  # #42 수동 생성 곡수 1~100(미지정→1). test_render 는 무시.


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
    """수동 영상 생성(#26) — 진짜 음원 N곡 → 풀 렌더 → 검토 큐 적재(비동기). 유튜브 X.

    수 분~수십 분 걸려 BackgroundTasks 로 시작하고 job_id 즉시 반환. 동시 1개 제한.
    완료 시 music_uploads 에 status=pending 으로 저장(검토 큐 일반 카드). 상태는
    GET /manual-render/status/{job_id} 폴링. track_count(#42): 곡수 1~100(미지정→1).
    """
    from services import music_manual
    started = music_manual.start(
        mood=body.mood if body else None,
        track_count=body.track_count if body else None,
    )
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


@router.get("/jobs/active")
def jobs_active():
    """진행 중(+미확인 실패) 작업 목록 — 대시보드 파이프라인·검토대기 진행 카드용(#36)."""
    from services import music_jobs
    return {"jobs": music_jobs.list_active()}


@router.get("/jobs/history")
def jobs_history(limit: int = 20):
    """최근 완료/실패 작업 — 대시보드 통계용(#36)."""
    from services import music_jobs
    return {"jobs": music_jobs.list_history(limit)}


@router.get("/jobs/{job_id}")
def jobs_detail(job_id: str):
    """특정 작업 상세(#36). 없으면 404."""
    from services import music_jobs
    job = music_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="해당 job 을 찾을 수 없습니다.")
    return {"job": job}


@router.post("/jobs/{job_id}/dismiss")
def jobs_dismiss(job_id: str):
    """실패 카드 [닫기](#36) — active 목록에서 제거(상태는 failed 보존)."""
    from services import music_jobs
    res = music_jobs.dismiss_job(job_id)
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail=res.get("error") or "닫기 실패")
    return {"ok": True}


@router.post("/jobs/{job_id}/retry")
def jobs_retry(job_id: str, background: BackgroundTasks):
    """실패 카드 [재시도](#36) — 같은 종류 작업을 다시 시작. 기존 실패 건은 닫는다.

    manual_render: 같은 mood 로 재생성 / rerender: 같은 mix_id 로 재렌더.
    cron 작업은 다음 cron 이 자동 재시도하므로 재시도 버튼 미지원(400).
    """
    from services import music_jobs
    job = music_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="해당 job 을 찾을 수 없습니다.")
    jtype = job.get("type")
    meta = job.get("metadata") or {}
    if jtype == "manual_render":
        from services import music_manual
        started = music_manual.start(mood=meta.get("mood"))
        if not started.get("ok"):
            raise HTTPException(status_code=409, detail=started.get("error") or "이미 진행 중")
        music_jobs.dismiss_job(job_id)
        background.add_task(music_manual.run, started["job_id"])
        return {"ok": True, "job_id": started["job_id"]}
    if jtype == "rerender":
        mix_id = job.get("mix_id")
        if not mix_id:
            raise HTTPException(status_code=400, detail="mix_id 가 없어 재렌더할 수 없습니다.")
        from services import music_rerender
        started = music_rerender.start(mix_id)
        if not started.get("ok"):
            raise HTTPException(status_code=409, detail=started.get("error") or "이미 진행 중")
        music_jobs.dismiss_job(job_id)
        background.add_task(music_rerender.run, started["job_id"])
        return {"ok": True, "job_id": started["job_id"]}
    raise HTTPException(status_code=400, detail="이 작업은 재시도를 지원하지 않습니다(cron 은 자동 재시도).")


@router.get("/design-config")
def design_config_get():
    """디자인 설정(PLAY LIST·Where 폰트/크기/두께/색/투명도/테두리) 조회(#35-A).

    저장값 없으면 기본값 반환(UI 초기 표시용). 렌더는 별도로 None 일 때 현재값 폴백.
    """
    from services import music_channel
    # UI 는 4개 패널 전부 필요 → include_all 로 title/subtitle 기본값까지 채워 반환(렌더 경로와 분리).
    cfg = music_channel.normalize_design_config(music_channel.get_design_config() or {}, include_all=True)
    return {"design_config": cfg, "presets": list(music_channel.PRESET_FONTS)}


class _DesignBorder(BaseModel):
    enabled: bool | None = None
    width: float | None = None
    color: str | None = None


class _DesignTarget(BaseModel):
    font_family: str | None = None
    font_size: float | None = None
    font_weight: float | None = None
    color: str | None = None
    opacity: float | None = None
    italic: bool | None = None  # #36 title/subtitle 만 사용(play_list/where_label 은 무시)
    border: _DesignBorder | None = None


class DesignConfigBody(BaseModel):
    play_list: _DesignTarget | None = None
    where_label: _DesignTarget | None = None
    title: _DesignTarget | None = None       # #36 곡 제목
    subtitle: _DesignTarget | None = None     # #36 부제


@router.post("/design-config")
def design_config_set(body: DesignConfigBody):
    """디자인 설정 저장(#35-A) — 검증·정규화 후 channel_status.design_config 에 upsert.

    다음 영상부터 자동 적용. 기존 영상은 /music/queue 재렌더로 반영.
    """
    from services import music_channel
    res = music_channel.set_design_config(body.model_dump(exclude_none=True))
    if not res.get("ok"):
        raise HTTPException(status_code=502, detail=res.get("error") or "저장 실패")
    cfg = music_channel.normalize_design_config(music_channel.get_design_config() or {}, include_all=True)
    return {"ok": True, "design_config": cfg}


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
