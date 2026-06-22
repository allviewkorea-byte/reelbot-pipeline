"""주제 생성기 (Rooftop Music) — 주제 헌법으로 코히어런트한 새 주제 1개 랜덤 생성.

prompts/music_themes.md(주제 헌법, SSOT)를 매 호출 읽고 Anthropic(저렴한 Haiku)으로
새 주제 1개를 1번 스키마 JSON 으로 뽑는다. 최근 장르와 안 겹치게 dedup 하고
Supabase music_themes 에 기록한다. 보컬/연주 라우팅(type)은 헌법 3번이 정한다.

재사용(신규 의존성·SDK·LLM 클라이언트 추가 없음):
  - Anthropic 호출 + JSON 추출: services.music_lyrics._call / _extract_json
  - Supabase PostgREST: services.music_store._supabase_cfg / _http_err 패턴

모델: 기본 claude-haiku-4-5-20251001(주제 뽑기는 조합·판단이라 싼 모델로 충분),
env MUSIC_THEME_MODEL 로 교체. 가사만 Sonnet/Opus(music_lyrics) 를 탄다.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx

from services import music_lyrics
from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

# 주제 헌법 경로(이 파일 기준 ../prompts/).
_THEMES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "music_themes.md"

_TABLE = "music_themes"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# 스키마 검증.
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")
_REQUIRED = ("slug", "title_kr", "genre", "situation", "mood", "type", "style_prompt")
_VALID_TYPES = ("vocal", "instrumental")
_DEFAULT_TRACK_COUNT = 1  # #30 비용 절감 — 영상 1개당 suno 1회(12크레딧). 대시보드에서 곡수 조절.


def _model(model: str | None = None) -> str:
    return (model or os.getenv("MUSIC_THEME_MODEL") or _DEFAULT_MODEL).strip()


def is_available() -> bool:
    """가사와 동일하게 ANTHROPIC_API_KEY 로 가용성 판단."""
    return music_lyrics.is_available()


def load_catalog() -> str:
    """주제 헌법 로드. 없으면 빈 문자열(생성은 진행하되 경고)."""
    try:
        return _THEMES_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning("주제 헌법 파일 없음: %s", _THEMES_PATH)
        return ""


# ── Supabase (music_store PostgREST 패턴 재사용) ──────────────────────────
def list_recent_themes(n: int = 10) -> list[dict]:
    """music_themes 에서 최근 n개의 {slug, genre, situation} 조회(created_at 역순).

    미설정/오류 시 빈 리스트(dedup 은 메모리 누적분으로만 동작).
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[theme] SUPABASE 미설정 — 최근 주제 조회 생략")
        return []
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "select": "slug,genre,situation",
            "order": "created_at.desc",
            "limit": str(n),
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[theme] 최근 주제 조회 실패: %s", _http_err(e))
        return []


def get_theme(slug: str) -> dict | None:
    """slug 로 저장된 주제 1개 조회. payload(원본 JSON) 우선 반환. 없으면 None."""
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[theme] SUPABASE 미설정 — 주제 조회 불가")
        return None
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=headers,
                params={"slug": f"eq.{slug}", "select": "*", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        if not rows:
            return None
        row = rows[0]
        payload = row.get("payload")
        return payload if isinstance(payload, dict) and payload else row
    except Exception as e:  # noqa: BLE001
        logger.warning("[theme] 주제 조회 실패(%s): %s", slug, _http_err(e))
        return None


def _slug_exists(slug: str) -> bool:
    """slug 이 DB 에 이미 있는지(전역 dedup). 미설정/오류 시 False."""
    url, key = _supabase_cfg()
    if not (url and key):
        return False
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=headers,
                params={"slug": f"eq.{slug}", "select": "slug", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        return bool(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("[theme] slug 존재 확인 실패(%s): %s", slug, _http_err(e))
        return False


def save_theme(theme: dict) -> dict:
    """주제 1개를 music_themes 에 upsert(slug 충돌 시 병합). {stored, error} 반환."""
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[theme] SUPABASE 미설정 — 주제 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    record = {
        "slug": theme.get("slug"),
        "title_kr": theme.get("title_kr"),
        "genre": theme.get("genre"),
        "situation": theme.get("situation"),
        "mood": theme.get("mood"),
        "type": theme.get("type"),
        "style_prompt": theme.get("style_prompt"),
        "lyric_tone": theme.get("lyric_tone"),
        "track_count": theme.get("track_count"),
        "payload": theme,
    }
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=slug",
                headers=headers,
                json=[record],
            )
            r.raise_for_status()
        logger.info("[theme] 저장 OK (slug=%s)", record.get("slug"))
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[theme] 저장 실패(slug=%s): %s", record.get("slug"), msg)
        return {"stored": False, "error": msg}


# ── 검증 ─────────────────────────────────────────────────────────────────
def _validate(theme: dict) -> dict:
    """스키마 검증 + 정규화. 위반 시 ValueError. type 에 맞춰 lyric_tone/track_count 보정."""
    if not isinstance(theme, dict):
        raise ValueError("주제가 dict 가 아닙니다.")
    for k in _REQUIRED:
        if not str(theme.get(k) or "").strip():
            raise ValueError(f"필수 키 누락/빈값: {k}")

    slug = str(theme["slug"]).strip()
    if not _SLUG_RE.match(slug):
        raise ValueError(f"slug 형식 위반(^[a-z0-9_]+$): {slug!r}")

    t = str(theme["type"]).strip().lower()
    if t not in _VALID_TYPES:
        raise ValueError(f"type 은 vocal|instrumental: {theme.get('type')!r}")

    # 라우팅별 lyric_tone 규칙.
    if t == "instrumental":
        theme["lyric_tone"] = None  # 연주는 가사 없음
    else:  # vocal
        if not str(theme.get("lyric_tone") or "").strip():
            raise ValueError("vocal 주제는 lyric_tone 이 필요합니다.")

    # track_count 정규화(없거나 이상하면 기본 8).
    try:
        tc = int(theme.get("track_count") or _DEFAULT_TRACK_COUNT)
    except (TypeError, ValueError):
        tc = _DEFAULT_TRACK_COUNT
    theme["slug"] = slug
    theme["type"] = t
    theme["track_count"] = max(1, tc)
    return theme


# ── 생성 ─────────────────────────────────────────────────────────────────
def _trend_hint() -> str:
    """최신 트렌드 인사이트 → 주제 생성 프롬프트에 끼울 '영감' 문구(가중치 아님).

    인사이트가 없으면 빈 문자열(기존 로직 회귀 0). 특정 주제 강제·빈도 조작은 절대 안 함.
    """
    try:
        from services import music_trend
        ins = music_trend.get_latest()
    except Exception:  # noqa: BLE001 - 조회 실패 → 영감 없이 진행
        return ""
    if not ins:
        return ""
    moods = ", ".join(str(x) for x in (ins.get("mood_keywords") or []))
    titles = ", ".join(str(x) for x in (ins.get("title_patterns") or []))
    summary = str(ins.get("summary") or "")
    if not (moods or titles or summary):
        return ""
    return (
        "\n\n[요즘 트렌드 — 영감용(가중치/빈도 조작 아님)]\n"
        f"- 잘 되는 무드: {moods}\n"
        f"- 제목 경향: {titles}\n"
        f"- 인사이트: {summary}\n"
        "이 결을 참고하되 그대로 베끼지 말고 우리 채널 톤으로 재해석하라. "
        "특정 주제를 강제 선택하거나 빈도를 높이지 말 것 — 다양성(5번)이 우선."
    )


def _build_messages(
    catalog: str,
    recent_genres: list[str],
    recent_situations: list[str],
    trend_hint: str = "",
) -> tuple[str, str]:
    system = (
        "너는 루프탑뮤직의 주제 큐레이터다. 아래 '주제 헌법'(SSOT)을 절대 기준으로 삼아 "
        "코히어런트한 새 주제 1개를 뽑는다. 모순 조합(수면 EDM, 운동 앰비언트 등) 금지.\n\n"
        f"=== 주제 헌법 ===\n{catalog}"
    )
    avoid_g = ", ".join(recent_genres) if recent_genres else "(없음)"
    avoid_s = ", ".join(recent_situations) if recent_situations else "(없음)"
    user = (
        "위 가이드를 따라 **새 주제 1개만** 1번 출력 스키마의 JSON으로 출력하라.\n"
        f"- 최근 장르 {avoid_g} 는 피한다(5번 다양성).\n"
        f"- 최근 상황 {avoid_s} 와 연속되지 않게 한다.\n"
        "- 4번 코히어런스(상황×무드×장르가 말 되는 조합)·6번 style_prompt 작성법을 지킨다.\n"
        "- type 이 instrumental 이면 lyric_tone 은 null, vocal 이면 lyric_tone 한 줄을 채운다.\n"
        "- slug 은 영문 소문자_스네이크(^[a-z0-9_]+$).\n"
        f"{trend_hint}\n"
        "**JSON 외 다른 텍스트 금지.**"
    )
    return system, user


def generate_theme(
    *,
    avoid_recent: int = 10,
    model: str | None = None,
    max_tries: int = 4,
    persist: bool = True,
    extra_recent: list[dict] | None = None,
) -> dict:
    """코히어런트한 새 주제 1개 생성 → dedup → (옵션) 저장 → theme dict 반환.

    extra_recent: DB 최근분 외 추가로 피할 주제(예: 같은 실행에서 이미 뽑은 것). 메모리 dedup.
    저장 실패해도 dict 는 반환한다(생성 자체는 성공).
    """
    if not is_available():
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — 주제 생성 불가")

    catalog = load_catalog()
    recent = list_recent_themes(avoid_recent) + list(extra_recent or [])
    recent_slugs = {str(t.get("slug") or "").strip() for t in recent if t.get("slug")}
    recent_genres = [str(t.get("genre") or "").strip() for t in recent if t.get("genre")]
    recent_situations = [
        str(t.get("situation") or "").strip() for t in recent if t.get("situation")
    ]
    mdl = _model(model)

    system, user = _build_messages(
        catalog, recent_genres, recent_situations, trend_hint=_trend_hint()
    )

    last: dict | None = None
    for attempt in range(1, max_tries + 1):
        try:
            raw = music_lyrics._call(system, user, max_tokens=700, model=mdl)
            theme = _validate(music_lyrics._extract_json(raw))
        except Exception as e:  # noqa: BLE001 - 형식/검증 실패 → 재시도
            logger.warning("[theme] 시도 %d 생성/검증 실패: %s", attempt, e)
            continue
        last = theme
        # dedup: slug 중복(메모리 또는 DB) 또는 최근 장르와 겹치면 재생성.
        dup_slug = theme["slug"] in recent_slugs or (persist and _slug_exists(theme["slug"]))
        dup_genre = theme.get("genre") in recent_genres
        if dup_slug or dup_genre:
            logger.info(
                "[theme] 시도 %d 중복(slug=%s genre=%s) — 재생성",
                attempt, dup_slug, dup_genre,
            )
            continue
        break
    else:
        # 모든 시도가 dedup 실패 → 마지막 유효 결과 사용(경고).
        if last is None:
            raise RuntimeError(f"주제 생성 실패(유효 결과 없음, {max_tries}회 시도)")
        logger.warning(
            "[theme] dedup %d회 실패 — 마지막 결과 사용(slug=%s)", max_tries, last["slug"]
        )
        theme = last

    if persist:
        save_theme(theme)  # 실패해도 dict 반환(생성은 성공)
    return theme
