"""트렌드 자동 분석 스케줄러 (APScheduler).

매일 새벽 4시(KST), trend 설정이 enabled 인 채널의
카테고리 × 형식 조합을 분석한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from services import trend_settings_store
from services.trend_analyzer import analyze_category

logger = logging.getLogger("reelbot.scheduler")

_scheduler: BackgroundScheduler | None = None
_KST_OFFSET_HOURS = 9


def run_channel_analysis(channel_id: str, settings: dict) -> None:
    """단일 채널의 모든 카테고리 × 형식 조합을 분석한다 (예외는 로깅만)."""
    keywords = settings.get("keywords") or []
    categories = settings.get("categories") or []
    formats = settings.get("formats") or ["shorts", "long"]

    for category in categories:
        for fmt in formats:
            try:
                analyze_category(channel_id, category, fmt, keywords)
            except Exception:  # noqa: BLE001 - 한 조합 실패가 전체를 막지 않도록
                logger.exception(
                    "트렌드 분석 실패: channel=%s category=%s format=%s",
                    channel_id,
                    category,
                    fmt,
                )

    trend_settings_store.touch_last_analyzed(
        channel_id, datetime.now(timezone.utc).isoformat()
    )


def run_daily_analysis() -> None:
    """enabled + schedule=daily 인 모든 채널을 분석한다."""
    logger.info("일일 트렌드 분석 시작")
    for settings in trend_settings_store.all_settings():
        if not settings.get("enabled"):
            continue
        if settings.get("schedule") != "daily":
            continue
        channel_id = settings.get("channelId")
        if not channel_id:
            continue
        run_channel_analysis(channel_id, settings)
    logger.info("일일 트렌드 분석 종료")


def start_scheduler() -> BackgroundScheduler:
    """FastAPI lifespan 에서 호출. 매일 04:00 KST 트리거를 등록한다."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    # APScheduler 의 cron timezone 을 KST 로 직접 지정할 수 없는 환경을 대비해
    # UTC 기준 19시(= KST 04시)로 변환해 등록한다.
    utc_hour = (4 - _KST_OFFSET_HOURS) % 24
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_daily_analysis,
        trigger=CronTrigger(hour=utc_hour, minute=0),
        id="daily_trend_analysis",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("트렌드 스케줄러 시작 (매일 04:00 KST)")
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
