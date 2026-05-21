"""트렌드 분석 API 라우터.

- POST /trends/analyze                       즉시 분석 트리거 (백그라운드 job)
- GET  /trends/{channel_id}                  저장된 분석 결과 조회
- PUT  /channels/{channel_id}/trend-settings 자동 분석 설정 업데이트
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks

from api.jobs import job_manager
from models.trend import TrendAnalyzeRequest, TrendAnalyzeResponse, TrendSettings
from services import trend_settings_store
from services.trend_analyzer import analyze_category, load_insights

router = APIRouter()
channels_router = APIRouter()


def _run_analysis(
    job_id: str,
    channel_id: str,
    keywords: list[str],
    categories: list[str],
    formats: list[str],
) -> None:
    job_manager.start_job(job_id)
    try:
        combos = [(c, f) for c in categories for f in formats]
        total = max(len(combos), 1)
        results: list[dict] = []

        for idx, (category, fmt) in enumerate(combos):
            base = int(idx / total * 100)

            def cb(pct: int, msg: str, _base=base, _total=total):
                job_manager.update_progress(
                    job_id, min(99, _base + pct // _total), f"{category}/{fmt}: {msg}"
                )

            insight = analyze_category(channel_id, category, fmt, keywords, progress_cb=cb)
            results.append(insight)

        trend_settings_store.touch_last_analyzed(
            channel_id, datetime.now(timezone.utc).isoformat()
        )
        job_manager.complete_job(job_id, {"insights": results})
    except Exception as e:  # noqa: BLE001
        job_manager.fail_job(job_id, str(e))


@router.post("/analyze", response_model=TrendAnalyzeResponse)
def analyze(req: TrendAnalyzeRequest, background: BackgroundTasks):
    """카테고리 × 형식 조합을 백그라운드에서 분석한다."""
    # 설정이 비어있으면 저장된 채널 설정을 fallback 으로 사용
    settings = trend_settings_store.get_settings(req.channel_id)
    keywords = req.keywords or settings.get("keywords") or []
    categories = req.categories or settings.get("categories") or []
    formats = req.formats or settings.get("formats") or ["shorts", "long"]

    job = job_manager.create_job("trend")
    background.add_task(
        _run_analysis, job.job_id, req.channel_id, keywords, categories, list(formats)
    )
    return TrendAnalyzeResponse(job_id=job.job_id, status=job.status.value)


@router.get("/{channel_id}")
def get_trends(channel_id: str, category: str | None = None, format: str | None = None):
    """저장된 분석 결과 조회. ?category=&format= 으로 필터링."""
    insights = load_insights(channel_id, category, format)
    return {"channelId": channel_id, "insights": insights}


@channels_router.put("/channels/{channel_id}/trend-settings")
def update_trend_settings(channel_id: str, settings: TrendSettings):
    """채널의 자동 분석 설정을 저장한다."""
    payload = settings.model_dump(by_alias=True)
    saved = trend_settings_store.save_settings(channel_id, payload)
    return {"channelId": channel_id, "settings": saved}
