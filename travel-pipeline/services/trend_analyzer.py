"""트렌드 분석 모듈.

키워드 → YouTube 인기 영상 수집 → 통계 + gpt-4o-mini 분석 → TrendInsight JSON 저장.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from openai import OpenAI

from adapters.data.youtube_data_adapter import YouTubeDataAdapter

VideoFormat = Literal["shorts", "long"]

_TRENDS_DIR = Path(__file__).resolve().parent.parent / "data" / "trends"
_OPENAI_MODEL = "gpt-4o-mini"

ProgressCb = Callable[[int, str], None]


def _trend_path(channel_id: str, category: str, format: VideoFormat) -> Path:
    safe_cat = category.replace("/", "_").replace(" ", "_")
    return _TRENDS_DIR / f"{channel_id}_{safe_cat}_{format}.json"


def _openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _chat_json(client: OpenAI, prompt: str) -> dict:
    """gpt-4o-mini 를 JSON 모드로 호출하고 dict 를 반환한다."""
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def _analyze_power_words(client: OpenAI, titles: list[str]) -> list[dict]:
    if not titles:
        return []
    joined = "\n".join(f"- {t}" for t in titles[:50])
    prompt = (
        "다음은 인기 유튜브 영상 제목 목록입니다. 제목에서 클릭을 유도하는 "
        '"파워 워드"(예: 놀라운, 최고, 비밀, 꿀팁, 충격, 완벽)를 추출하고 등장 빈도를 세어주세요.\n\n'
        f"{joined}\n\n"
        '반드시 JSON 형식만 응답: {"powerWords":[{"word":"단어","count":3}]} (count 내림차순, 최대 10개)'
    )
    data = _chat_json(client, prompt)
    words = data.get("powerWords", [])
    out: list[dict] = []
    for w in words:
        if isinstance(w, dict) and w.get("word"):
            out.append({"word": str(w["word"]), "count": int(w.get("count", 1) or 1)})
    return out[:10]


def _classify_tags(client: OpenAI, tags: list[str], category: str) -> dict:
    base = {"primary": [], "variants": [], "competitor": [], "broad": [], "niche": []}
    if not tags:
        return base
    uniq = list(dict.fromkeys(tags))[:80]
    joined = ", ".join(uniq)
    prompt = (
        f'"{category}" 카테고리의 인기 영상에서 수집한 태그들을 5가지로 분류해주세요.\n\n'
        f"태그: {joined}\n\n"
        "분류 기준:\n"
        "- primary: 검색 의도와 직결되는 주요 키워드\n"
        "- variants: 동의어·표현 차이 같은 변형어\n"
        "- competitor: 경쟁 채널이 자주 쓰는 태그\n"
        "- broad: 광범위한 카테고리 태그\n"
        "- niche: 좁은 세부 태그\n\n"
        '반드시 JSON 형식만 응답: '
        '{"primary":[],"variants":[],"competitor":[],"broad":[],"niche":[]}'
    )
    data = _chat_json(client, prompt)
    for key in base:
        vals = data.get(key, [])
        if isinstance(vals, list):
            base[key] = [str(v) for v in vals if v][:15]
    return base


def _analyze_description_pattern(client: OpenAI, descriptions: list[str]) -> dict:
    out = {"first150Keywords": [], "hookStructure": ""}
    snippets = [d[:150] for d in descriptions if d][:30]
    if not snippets:
        return out
    joined = "\n---\n".join(snippets)
    prompt = (
        "다음은 인기 영상 설명의 첫 100~150자 모음입니다. 자주 등장하는 핵심 키워드와 "
        "공통된 후크(첫 문장) 구조를 분석해주세요.\n\n"
        f"{joined}\n\n"
        '반드시 JSON 형식만 응답: '
        '{"first150Keywords":["키워드"],"hookStructure":"공통 후크 구조 한 줄 설명"}'
    )
    data = _chat_json(client, prompt)
    kws = data.get("first150Keywords", [])
    if isinstance(kws, list):
        out["first150Keywords"] = [str(k) for k in kws if k][:15]
    out["hookStructure"] = str(data.get("hookStructure", ""))
    return out


def _analyze_hook_patterns(client: OpenAI, titles: list[str]) -> list[str]:
    if not titles:
        return []
    joined = "\n".join(f"- {t}" for t in titles[:40])
    prompt = (
        "다음 인기 영상 제목들을 보고, 첫 3초 후크로 자주 쓰이는 패턴 5가지를 "
        "짧은 한국어 문장으로 정리해주세요.\n\n"
        f"{joined}\n\n"
        '반드시 JSON 형식만 응답: {"hookPatterns":["패턴 설명"]}'
    )
    data = _chat_json(client, prompt)
    hooks = data.get("hookPatterns", [])
    return [str(h) for h in hooks if h][:5] if isinstance(hooks, list) else []


def _analyze_comments(client: OpenAI, comments: list[str]) -> dict:
    out = {
        "sentiment": {"positive": 0.0, "negative": 0.0, "neutral": 0.0},
        "faqs": [],
        "contentIdeas": [],
    }
    if not comments:
        return out
    joined = "\n".join(f"- {c[:200]}" for c in comments[:120])
    prompt = (
        "다음은 인기 영상 댓글 모음입니다. 분석해주세요.\n\n"
        f"{joined}\n\n"
        "1) 감정 비율(긍정/부정/중립, 합이 1.0)\n"
        "2) 자주 묻는 질문 TOP 5\n"
        "3) 시청자가 요청한 후속 영상 아이디어\n\n"
        '반드시 JSON 형식만 응답: '
        '{"sentiment":{"positive":0.6,"negative":0.1,"neutral":0.3},'
        '"faqs":["질문"],"contentIdeas":["아이디어"]}'
    )
    data = _chat_json(client, prompt)
    s = data.get("sentiment", {})
    if isinstance(s, dict):
        out["sentiment"] = {
            "positive": float(s.get("positive", 0) or 0),
            "negative": float(s.get("negative", 0) or 0),
            "neutral": float(s.get("neutral", 0) or 0),
        }
    if isinstance(data.get("faqs"), list):
        out["faqs"] = [str(q) for q in data["faqs"] if q][:5]
    if isinstance(data.get("contentIdeas"), list):
        out["contentIdeas"] = [str(i) for i in data["contentIdeas"] if i][:5]
    return out


def _popular_upload_hours(published_ats: list[str]) -> list[int]:
    """게시 시간(UTC ISO)을 KST 시(0-23) 분포로 집계해 상위 3개 시간대를 반환."""
    counts: dict[int, int] = {}
    for ts in published_ats:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            kst_hour = (dt.astimezone(timezone.utc).hour + 9) % 24
            counts[kst_hour] = counts.get(kst_hour, 0) + 1
        except (ValueError, AttributeError):
            continue
    return [h for h, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:3]]


def analyze_category(
    channel_id: str,
    category: str,
    format: VideoFormat,
    keywords: list[str],
    *,
    progress_cb: ProgressCb | None = None,
) -> dict:
    """단일 카테고리 × 형식 트렌드 분석을 수행하고 결과 dict 를 반환·저장한다."""

    def report(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    yt = YouTubeDataAdapter()
    if not yt.is_available():
        raise RuntimeError("YOUTUBE_API_KEY 가 설정되지 않아 트렌드 분석을 할 수 없습니다.")

    report(5, "인기 영상 검색 중")
    videos: list[dict] = []
    yt_format = format  # "shorts" | "long"
    seen_ids: set[str] = set()
    for kw in keywords or [category]:
        for v in yt.search_top_videos(kw, format=yt_format, max_results=50):
            if v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                videos.append(v)

    videos.sort(key=lambda v: v["view_count"], reverse=True)
    videos = videos[:50]

    report(35, "영상 통계 집계 중")
    durations = [v["duration_sec"] for v in videos if v["duration_sec"] > 0]
    titles = [v["title"] for v in videos if v["title"]]
    descriptions = [v["description"] for v in videos if v["description"]]
    all_tags: list[str] = []
    for v in videos:
        all_tags.extend(v.get("tags", []))

    avg_len = round(statistics.mean(durations), 1) if durations else 0.0
    avg_title_len = round(statistics.mean([len(t) for t in titles]), 1) if titles else 0.0

    client = _openai_client()

    report(50, "제목 패턴 분석 중")
    power_words = _analyze_power_words(client, titles)
    hook_patterns = _analyze_hook_patterns(client, titles)

    report(65, "설명·태그 분석 중")
    desc_pattern = _analyze_description_pattern(client, descriptions)
    tags_by_cat = _classify_tags(client, all_tags, category)

    report(80, "댓글 수집·분석 중")
    comments: list[str] = []
    for v in videos[:5]:
        comments.extend(yt.get_video_comments(v["id"], max_count=40))
    comment_insights = _analyze_comments(client, comments)

    report(92, "업로드 시간대 집계 중")
    upload_hours = _popular_upload_hours([v["published_at"] for v in videos])

    insight = {
        "channelId": channel_id,
        "category": category,
        "format": format,
        "analyzedAt": datetime.now(timezone.utc).isoformat(),
        "avgVideoLengthSec": avg_len,
        "avgTitleLength": avg_title_len,
        "powerWords": power_words,
        "descriptionPattern": desc_pattern,
        "tagsByCategory": tags_by_cat,
        "hookPatterns": hook_patterns,
        "popularUploadHours": upload_hours,
        "commentInsights": comment_insights,
        "_meta": {
            "videoCount": len(videos),
            "commentCount": len(comments),
            "quotaUsed": yt.quota_used,
        },
    }

    _TRENDS_DIR.mkdir(parents=True, exist_ok=True)
    path = _trend_path(channel_id, category, format)
    path.write_text(json.dumps(insight, ensure_ascii=False, indent=2), encoding="utf-8")

    report(100, "완료")
    return insight


def load_insights(channel_id: str, category: str | None = None, format: str | None = None) -> list[dict]:
    """저장된 분석 결과를 조회한다. category/format 지정 시 필터링."""
    if not _TRENDS_DIR.exists():
        return []
    results: list[dict] = []
    for path in _TRENDS_DIR.glob(f"{channel_id}_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if category and data.get("category") != category:
            continue
        if format and data.get("format") != format:
            continue
        results.append(data)
    results.sort(key=lambda d: d.get("analyzedAt", ""), reverse=True)
    return results
