"""쇼츠 배경음악 소스 — 운동 채널에 **실제로 업로드된** 플리 영상 속 우리 곡 + 그 영상 링크(곡 위치).

곡 ID 와 업로드 행은 바로 이어지지 않는다(라이브러리 영상은 새 slug 를 쓴다). 유일한 연결 고리는
R2 믹스 JSON 이다:
  music_uploads(status=uploaded, channel) → slug·mix_id·youtube_url
  → music-mixes/{slug}/{mix_id}.json 의 tracks[{audio_id, title, language, start_sec}]
  → music_tracks(r2_key) → 마스터본(업로드 slug 아래) 또는 원본 오디오 URL
쇼츠 → 채널 유입: 곡이 들어간 플리 영상 링크 + 그 영상 안에서 후렴 위치(&t=)를 함께 준다.

선택 규칙(0단계 승인): 최근 30일 업로드 영상 속 곡 · 연주곡 → 영어 순 · 최근 쇼츠에 쓴 곡 제외.
분석 결과(BPM·드롭·후렴)는 R2 shorts/{channel}/song_analysis.json 에 캐시(SQL 없음).
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from adapters import r2_storage

logger = logging.getLogger(__name__)

CHANNEL = "workout_music"
_LANG_RANK = {"inst": 0, "en": 1}


def recent_uploads(channel: str = CHANNEL, *, days: int = 30, limit: int = 30) -> list[dict]:
    """최근 업로드 완료된 플리 영상 행(최신순). 오류·미설정 → []."""
    from services.music_store import _http_err, _supabase_cfg
    from services.music_uploads import _headers, _resolve_channel
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(f"{url}/rest/v1/music_uploads", headers=_headers(key), params={
                "status": "eq.uploaded", "channel": f"eq.{_resolve_channel(channel)}",
                "uploaded_at": f"gte.{since}", "youtube_url": "not.is.null",
                "select": "slug,mix_id,youtube_video_id,youtube_url,tag_combo,uploaded_at",
                "order": "uploaded_at.desc", "limit": str(limit)})
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-songs] 업로드 영상 조회 실패: %s", _http_err(e))
        return []


def link_at(youtube_url: str, seconds: float) -> str:
    """플리 영상 링크 + 곡 위치(t=초)."""
    sep = "&" if "?" in youtube_url else "?"
    return f"{youtube_url}{sep}t={max(0, int(seconds))}s"


def mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def _audio_url(upload_slug: str, audio_id: str, r2_key: str) -> str:
    """마스터본(-14 LUFS, 업로드 slug 아래)이 있으면 그것, 없으면 원본."""
    try:
        if r2_storage.mastered_music_exists(upload_slug, audio_id):
            return r2_storage.mastered_music_url(upload_slug, audio_id)
    except Exception:  # noqa: BLE001
        pass
    return r2_storage.music_object_url(r2_key)


def candidates(channel: str = CHANNEL, *, days: int = 30, exclude: set[str] | None = None,
               load_mix=None, get_tracks=None, uploads=None) -> list[dict]:
    """업로드된 플리 영상 속 곡 후보(연주곡 → 영어 → 그 외, 최신 영상 우선). 같은 곡은 1번만."""
    from services import music_recovery, music_store
    load_mix = load_mix or music_recovery._load_mix
    get_tracks = get_tracks or (lambda ids: music_store.get_tracks_by_ids(ids, channel=channel))
    exclude = exclude or set()
    seen: set[str] = set()
    out: list[dict] = []
    for up in uploads if uploads is not None else recent_uploads(channel, days=days):
        mix = load_mix(up["slug"], up["mix_id"]) or {}
        tracks = sorted(mix.get("tracks") or [], key=lambda t: t.get("start_sec") or 0)
        ids = [t.get("audio_id") for t in tracks if t.get("audio_id")]
        meta = {m.get("audio_id"): m for m in (get_tracks(ids) if ids else [])}
        total = float(mix.get("total_duration") or 0)
        for i, t in enumerate(tracks):
            aid = t.get("audio_id")
            m = meta.get(aid) or {}
            if not aid or aid in seen or aid in exclude or not m.get("r2_key"):
                continue
            seen.add(aid)
            start = float(t.get("start_sec") or 0)
            nxt = float(tracks[i + 1].get("start_sec") or 0) if i + 1 < len(tracks) else total
            out.append({
                "audio_id": aid, "title": t.get("title") or m.get("title") or "",
                "language": t.get("language") or m.get("language") or "",
                "audio_url": _audio_url(up["slug"], aid, m["r2_key"]),
                "youtube_url": up["youtube_url"], "video_id": up.get("youtube_video_id"),
                "start_in_video": round(start, 2),
                "duration": round(max(0.0, nxt - start), 2) or m.get("duration"),
                "uploaded_at": up.get("uploaded_at"), "slug": up["slug"], "mix_id": up["mix_id"],
            })
    out.sort(key=lambda c: _LANG_RANK.get(c["language"], 2))  # 안정 정렬 → 같은 순위는 최신 영상 먼저
    return out


# ── 분석 캐시 ────────────────────────────────────────────────────────────
def _key(channel: str) -> str:
    return f"shorts/{channel}/song_analysis.json"


def read_analysis(channel: str = CHANNEL) -> dict:
    if not r2_storage.is_available():
        return {}
    try:
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=_key(channel))
        data = json.loads(obj["Body"].read())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_analysis(channel: str, data: dict) -> None:
    r2_storage._get_client().put_object(
        Bucket=r2_storage._music_bucket(), Key=_key(channel),
        Body=json.dumps(data, ensure_ascii=False).encode(), ContentType="application/json")


def analyze_song(cand: dict, *, fetch=None) -> dict:
    """곡 1개 다운로드 → BPM·드롭·후렴 + 플리 영상 안 후렴 위치 링크."""
    from services import shorts_audio
    from services.sayeon_assemble import _fetch
    fetch = fetch or _fetch
    with tempfile.TemporaryDirectory(prefix="shorts_song_") as d:
        p = Path(d) / "song.mp3"
        fetch(cand["audio_url"], p)
        a = shorts_audio.analyze(str(p))
    pos = cand["start_in_video"] + a["chorus_start"]
    return {**cand, **a, "chorus_in_video": round(pos, 2), "chorus_link": link_at(cand["youtube_url"], pos),
            "chorus_mmss": mmss(pos), "analyzed_at": datetime.now(timezone.utc).isoformat()}


def analyze_top(channel: str = CHANNEL, *, n: int = 3, days: int = 30) -> list[dict]:
    """후보 상위 n곡 분석 → 캐시 저장. 실패한 곡은 error 로 남긴다."""
    cache = read_analysis(channel)
    results = []
    for cand in candidates(channel, days=days)[:n]:
        try:
            res = analyze_song(cand)
        except Exception as e:  # noqa: BLE001
            res = {**cand, "error": str(e)[:300]}
        cache[cand["audio_id"]] = res
        results.append(res)
    if r2_storage.is_available():
        _write_analysis(channel, cache)
    return results


def pick_analyzed(channel: str = CHANNEL, *, exclude: set[str] | None = None) -> dict | None:
    """분석된 곡 중 하나(연주곡 → 영어 순, 최근 사용 제외). 없으면 None."""
    exclude = exclude or set()
    rows = [v for k, v in read_analysis(channel).items() if k not in exclude and not v.get("error")]
    rows.sort(key=lambda c: c.get("analyzed_at") or "", reverse=True)          # 최근 분석 먼저
    rows.sort(key=lambda c: _LANG_RANK.get(c.get("language", ""), 2))           # 안정 정렬: 연주곡 → 영어
    return rows[0] if rows else None
