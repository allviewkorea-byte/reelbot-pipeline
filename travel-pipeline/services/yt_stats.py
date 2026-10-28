"""유튜브 성과 수집(대표 2026-10-28 "유튜브 성과 연동 + 시청 지속률").

매일 점검(ops_report.run) 직전에 refresh():
  - 대상: music_uploads 중 youtube_video_id 가 있고 최근 RECENT_DAYS 일 안에 올린 영상(채널별)
  - YouTube Data API videos.list(statistics): 조회수·좋아요·댓글 — 지금 연결(youtube 권한)으로 가능
  - YouTube Analytics API: 평균 시청 시간·평균 시청 비율(시청 지속률) — yt-analytics.readonly 권한 필요.
    권한이 없으면(401/403) 그 채널은 "재연결 필요"로 표시하고 나머지는 계속.
  - yt_video_stats 에 (video_id, date) 1행씩(멱등 upsert)
report_summary(): 채널별 어제 대비 조회수 증가·최근 영상 상위/하위·평균 시청 비율·장르별 평균(인사이트).
제작 비중 자동 조정은 데이터가 1~2주 쌓인 뒤 다음 단계(지금은 리포트에 인사이트로만).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
TABLE = "yt_video_stats"
RECENT_DAYS = 60
DATA_API = "https://www.googleapis.com/youtube/v3/videos"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
CHANNELS = ("workout_music", "rooftop_music")
_LAST: dict = {}   # 마지막 refresh 상태(채널별 analytics 가능 여부 등) — 리포트에 같이 싣는다


def _rest(table: str, method: str = "GET", **kw) -> list[dict]:
    from services import insta_refs
    return insta_refs.rest(table, method, **kw)


def _token(channel: str) -> str:
    from services import music_youtube_oauth as yo
    return yo.get_credentials(channel).token


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def fetch_statistics(token: str, ids: list[str], http=None) -> dict[str, dict]:
    """videos.list(statistics) — 50개씩. → {video_id: {views, likes, comments}}."""
    out = {}
    with (http or httpx.Client(timeout=30.0)) as c:
        for part in _chunks(ids, 50):
            r = c.get(DATA_API, params={"part": "statistics", "id": ",".join(part)},
                      headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            for it in r.json().get("items") or []:
                st = it.get("statistics") or {}
                out[it["id"]] = {"views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                                 "comments": int(st.get("commentCount") or 0)}
    return out


def fetch_retention(token: str, ids: list[str], start: str, end: str, http=None) -> dict[str, dict]:
    """Analytics reports — 평균 시청 시간(초)·평균 시청 비율(%). 권한 없으면 PermissionError."""
    out = {}
    with (http or httpx.Client(timeout=30.0)) as c:
        for part in _chunks(ids, 50):
            r = c.get(ANALYTICS_API, headers={"Authorization": f"Bearer {token}"}, params={
                "ids": "channel==MINE", "startDate": start, "endDate": end, "dimensions": "video",
                "metrics": "views,averageViewDuration,averageViewPercentage", "filters": "video==" + ",".join(part),
                "maxResults": "200"})
            if r.status_code in (401, 403):
                raise PermissionError(f"애널리틱스 권한 없음(HTTP {r.status_code}) — 유튜브 재연결 필요")
            r.raise_for_status()
            cols = [h["name"] for h in r.json().get("columnHeaders") or []]
            for row in r.json().get("rows") or []:
                d = dict(zip(cols, row))
                out[d["video"]] = {"avg_view_sec": round(float(d.get("averageViewDuration") or 0), 1),
                                   "avg_view_pct": round(float(d.get("averageViewPercentage") or 0), 1)}
    return out


def refresh(now: datetime | None = None, *, token_fn=None, http=None) -> dict:
    """채널별 영상 성과를 오늘 날짜로 저장. → {channel: {videos, stats, retention}} 상태."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(KST).date()
    since = (now - timedelta(days=RECENT_DAYS)).isoformat()
    token_fn = token_fn or _token
    rows = _rest("music_uploads", params={
        "select": "channel,youtube_video_id,title_kr,genre,mood,uploaded_at", "youtube_video_id": "not.is.null",
        "uploaded_at": f"gte.{since}", "limit": "500"})
    by_ch: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("youtube_video_id") and r.get("channel") in CHANNELS:
            by_ch[r["channel"]].append(r)
    status: dict = {}
    out_rows = []
    for ch, vids in by_ch.items():
        st = {"videos": len(vids), "stats": "ok", "retention": "ok"}
        try:
            token = token_fn(ch)
        except Exception as e:  # noqa: BLE001
            status[ch] = {**st, "stats": f"연결 안 됨: {str(e)[:100]}", "retention": "-"}
            continue
        ids = [v["youtube_video_id"] for v in vids]
        try:
            stats = fetch_statistics(token, ids, http=http)
        except Exception as e:  # noqa: BLE001
            stats, st["stats"] = {}, f"실패: {str(e)[:100]}"
        try:
            oldest = min((v.get("uploaded_at") or now.isoformat())[:10] for v in vids)
            ret = fetch_retention(token, ids, oldest, today.isoformat(), http=http)
        except PermissionError as e:
            ret, st["retention"] = {}, str(e)
        except Exception as e:  # noqa: BLE001
            ret, st["retention"] = {}, f"실패: {str(e)[:100]}"
        for v in vids:
            vid = v["youtube_video_id"]
            if vid not in stats:
                continue
            out_rows.append({"video_id": vid, "date": today.isoformat(), "channel": ch, "title": v.get("title_kr"),
                             "genre": v.get("genre"), "mood": v.get("mood"), "uploaded_at": v.get("uploaded_at"),
                             **stats[vid], **ret.get(vid, {})})
        status[ch] = st
    for part in _chunks(out_rows, 200):
        _rest(TABLE, "POST", json_body=part, prefer="resolution=merge-duplicates,return=minimal",
              params={"on_conflict": "video_id,date"})
    _LAST.clear()
    _LAST.update({"at": now.isoformat(), "channels": status, "saved": len(out_rows)})
    return dict(_LAST)


def summarize_rows(today_rows: list[dict], prev_rows: list[dict], now: datetime) -> dict:
    """채널별 요약 — 어제 대비 조회수 증가, 최근 14일 업로드 상위/하위 3, 평균 시청 비율, 장르별 평균."""
    prev = {r["video_id"]: r for r in prev_rows}
    out = {}
    by_ch: dict[str, list[dict]] = defaultdict(list)
    for r in today_rows:
        by_ch[r["channel"]].append(r)
    cutoff14 = (now - timedelta(days=14)).isoformat()
    cutoff3 = (now - timedelta(days=3)).isoformat()
    for ch, rs in by_ch.items():
        gain = sum(max(0, r["views"] - prev.get(r["video_id"], {}).get("views", r["views"])) for r in rs)
        recent = sorted([r for r in rs if (r.get("uploaded_at") or "") >= cutoff14], key=lambda r: r["views"],
                        reverse=True)
        pcts = [r["avg_view_pct"] for r in rs if r.get("avg_view_pct")]
        genre = defaultdict(list)
        for r in rs:
            if r.get("genre") and (r.get("uploaded_at") or "") <= cutoff3:   # 3일 이상 지난 영상만 비교
                genre[r["genre"]].append(r["views"])
        brief = lambda r: {"title": (r.get("title") or "")[:40], "views": r["views"],  # noqa: E731
                           "avg_view_pct": r.get("avg_view_pct")}
        out[ch] = {"videos": len(rs), "total_views": sum(r["views"] for r in rs), "views_gain_1d": gain,
                   "avg_view_pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
                   "top_recent": [brief(r) for r in recent[:3]], "bottom_recent": [brief(r) for r in recent[-3:]][::-1]
                   if len(recent) > 3 else [],
                   "by_genre": {g: round(sum(v) / len(v)) for g, v in genre.items() if len(v) >= 2}}
    return out


def report_summary(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(KST).date()
    today_rows = _rest(TABLE, params={"select": "*", "date": f"eq.{today.isoformat()}", "limit": "1000"})
    prev_rows = _rest(TABLE, params={"select": "video_id,views", "date": f"eq.{(today - timedelta(days=1)).isoformat()}",
                                     "limit": "1000"})
    return {"channels": summarize_rows(today_rows, prev_rows, now), "status": dict(_LAST)}
