"""음악 채널 상태(channel_status) 읽기 — cron 이 곡수(track_count)를 읽는다(#30).

대시보드 토글이 channel_status(channel_id='rooftop_music')에 저장한 track_count 를
music cron(_run_produce)이 읽어 run_theme(n=track_count) 로 생성한다. 백곰과 같은
channel_status 테이블을 쓰되 channel_id 로 분리(같은 컬럼 재사용).
"""

from __future__ import annotations

import logging
import re

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

MUSIC_CHANNEL_ID = "rooftop_music"
_TABLE = "channel_status"
_MIN, _MAX = 1, 100  # #40 곡수 1~100(곡수↔길이 연동)
DEFAULT_TRACK_COUNT = 1


def _clamp(n: int) -> int:
    return max(_MIN, min(_MAX, n))


def get_track_count(default: int = DEFAULT_TRACK_COUNT) -> int:
    """음악 채널 곡수(1~8). 미설정/오류 시 default(=1). 안전 기본(과금 최소)."""
    url, key = _supabase_cfg()
    if not (url and key):
        return default
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{MUSIC_CHANNEL_ID}", "select": "track_count", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        if not rows:
            return default
        tc = rows[0].get("track_count")
        return _clamp(int(tc)) if tc is not None else default
    except Exception as e:  # noqa: BLE001 - 조회 실패 시 안전 기본(1)
        logger.warning("[music-channel] track_count 조회 실패(기본 %d): %s", default, _http_err(e))
        return default


# #37 채널 설정(슬로건·소셜·AI 명시) — channel_status.channel_config jsonb. 기본 AI 명시 문구 제공.
DEFAULT_AI_DISCLOSURE = (
    "💿 모든 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다. "
    "모든 이미지는 AI 생성 또는 라이선스 이미지를 사용합니다."
)
_CONFIG_KEYS = (
    "slogan_en", "slogan_kr", "email", "instagram", "tiktok", "spotify_url", "ai_disclosure",
)


def default_channel_config() -> dict:
    """빈 채널 설정(AI 명시만 기본값 채움). 프론트/백엔드 공통 기본."""
    return {k: (DEFAULT_AI_DISCLOSURE if k == "ai_disclosure" else "") for k in _CONFIG_KEYS}


def get_channel_config() -> dict:
    """음악 채널 설정(channel_config) 조회. 미설정/오류/컬럼 미존재 시 기본값(빈 칸 + 기본 AI 명시).

    공개 업로드 본문 조립(music_meta.build_description)에서 사용. 빈 값은 해당 섹션 생략.
    """
    base = default_channel_config()
    url, key = _supabase_cfg()
    if not (url and key):
        return base
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{MUSIC_CHANNEL_ID}", "select": "channel_config", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        cfg = (rows[0].get("channel_config") if rows else None) or {}
        if isinstance(cfg, dict):
            for k in _CONFIG_KEYS:
                v = cfg.get(k)
                if isinstance(v, str) and v.strip():
                    base[k] = v.strip()
        return base
    except Exception as e:  # noqa: BLE001 - 컬럼 미존재/오류 시 기본값
        logger.warning("[music-channel] channel_config 조회 실패(기본값 사용): %s", _http_err(e))
        return base


# #35-A 디자인 설정(PLAY LIST·Where 폰트·크기·두께·색·투명도·테두리) — channel_status.design_config jsonb.
# 프리셋 폰트 10종(프론트/Remotion 공통). UI 드롭다운·렌더 매핑이 같은 이름을 쓴다.
PRESET_FONTS = (
    "Montserrat", "Poppins", "Bebas Neue", "Oswald", "Anton",
    "Archivo", "Inter", "DM Sans", "Playfair Display", "Cormorant Garamond",
)

# UI 초기값(GET 기본). 비어 있을 때의 '렌더'는 MusicViz 가 현재 하드코딩값으로 폴백하므로,
# 이 기본값은 사용자가 디자인 본부를 처음 열었을 때 보이는 값일 뿐(저장 전엔 렌더 무영향).
# #36: title(곡 제목)·subtitle(부제) 추가 — italic 필드 포함(부제 기본 italic on = 현재 모습).
DEFAULT_DESIGN_CONFIG = {
    "play_list": {
        "font_family": "Playfair Display", "font_size": 324, "font_weight": 700,
        "color": "#FFFFFF", "opacity": 1.0,
        "border": {"enabled": False, "width": 2, "color": "#000000"},
    },
    "where_label": {
        "font_family": "Inter", "font_size": 24, "font_weight": 600,
        "color": "#FFFFFF", "opacity": 0.9,
        "border": {"enabled": False, "width": 1, "color": "#000000"},
    },
    "title": {
        "font_family": "Playfair Display", "font_size": 84, "font_weight": 700,
        "color": "#FFFFFF", "opacity": 1.0, "italic": False,
        "border": {"enabled": False, "width": 1, "color": "#000000"},
    },
    "subtitle": {
        "font_family": "Playfair Display", "font_size": 38, "font_weight": 400,
        "color": "#FFFFFF", "opacity": 1.0, "italic": True,
        "border": {"enabled": False, "width": 1, "color": "#000000"},
    },
}
# 항상 존재하는 핵심 대상(#35-A) vs 옵션 대상(#36, 저장됐을 때만 렌더에 포함 → 기존 row 회귀 0).
_CORE_TARGETS = ("play_list", "where_label")
_OPT_TARGETS = ("title", "subtitle")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex(v, dflt: str) -> str:
    return v if isinstance(v, str) and _HEX_RE.match(v.strip()) else dflt


def _num(v, lo: float, hi: float, dflt):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return dflt
    if n != n:  # NaN
        return dflt
    n = max(lo, min(hi, n))
    return int(round(n)) if isinstance(dflt, int) else round(n, 3)


def _norm_target(raw, dflt: dict) -> dict:
    out = dict(dflt)
    out["border"] = dict(dflt["border"])
    if isinstance(raw, dict):
        if raw.get("font_family") in PRESET_FONTS:
            out["font_family"] = raw["font_family"]
        out["font_size"] = _num(raw.get("font_size"), 8, 600, dflt["font_size"])
        out["font_weight"] = _num(raw.get("font_weight"), 100, 900, dflt["font_weight"])
        out["color"] = _hex(raw.get("color"), dflt["color"])
        out["opacity"] = _num(raw.get("opacity"), 0.0, 1.0, dflt["opacity"])
        if "italic" in dflt:  # #36 title/subtitle 만 italic 보유. 비bool 이면 기본값.
            iv = raw.get("italic", dflt["italic"])
            out["italic"] = iv if isinstance(iv, bool) else dflt["italic"]
        b = raw.get("border") if isinstance(raw.get("border"), dict) else {}
        out["border"] = {
            "enabled": bool(b.get("enabled", False)),
            "width": _num(b.get("width"), 0, 40, dflt["border"]["width"]),
            "color": _hex(b.get("color"), dflt["border"]["color"]),
        }
    return out


def normalize_design_config(raw, *, include_all: bool = False) -> dict:
    """제출/조회 데이터를 스키마로 정규화. 알 수 없는 키 무시, 값 클램프.

    핵심 대상(play_list/where_label)은 항상 포함(#35-A). 옵션 대상(title/subtitle, #36)은
    include_all 이거나 raw 에 실제로 있을 때만 포함 → 기존(#35-A) 저장 row 의 렌더 회귀 0
    (title/subtitle 키 없으면 MusicViz 가 현재 하드코딩값으로 폴백).
    """
    raw = raw if isinstance(raw, dict) else {}
    out = {name: _norm_target(raw.get(name), DEFAULT_DESIGN_CONFIG[name]) for name in _CORE_TARGETS}
    for name in _OPT_TARGETS:
        if include_all or isinstance(raw.get(name), dict):
            out[name] = _norm_target(raw.get(name), DEFAULT_DESIGN_CONFIG[name])
    return out


def default_design_config() -> dict:
    return normalize_design_config(DEFAULT_DESIGN_CONFIG, include_all=True)


def get_design_config() -> dict | None:
    """저장된 디자인 설정(정규화) 반환. 미저장/빈 객체/오류 시 None.

    렌더(make_video)는 None 이면 MusicViz 가 현재 하드코딩값으로 폴백 → 회귀 0.
    UI(GET)는 None 이면 default_design_config() 를 보여준다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return None
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{MUSIC_CHANNEL_ID}", "select": "design_config", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        cfg = (rows[0].get("design_config") if rows else None)
        if isinstance(cfg, dict) and (cfg.get("play_list") or cfg.get("where_label")):
            return normalize_design_config(cfg)
        return None
    except Exception as e:  # noqa: BLE001 - 컬럼 미존재/오류 시 None(현재값 폴백)
        logger.warning("[music-channel] design_config 조회 실패(현재값 폴백): %s", _http_err(e))
        return None


def set_design_config(cfg: dict) -> dict:
    """디자인 설정 저장(channel_status upsert, channel_id=rooftop_music). {ok, error}."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"ok": False, "error": "supabase 미설정"}
    record = {
        "channel_id": MUSIC_CHANNEL_ID,
        "design_config": normalize_design_config(cfg),
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=channel_id",
                headers={
                    "apikey": key, "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json=[record],
            )
            r.raise_for_status()
        return {"ok": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _http_err(e)}
