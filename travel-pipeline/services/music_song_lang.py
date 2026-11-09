"""영상별 가사 언어·연주 결정(대표 결정 2026-10-19 정정) — 운동·where 공통.

영상 1개는 한 가지로 통일한다(곡마다 섞지 않는다). 한 달 전체에서 비율이 맞도록 영상마다 랜덤:
  1) 연주 영상 = MUSIC_INSTRUMENTAL_RATE(기본 0.25)
  2) 나머지(보컬 영상) 중 영어 = MUSIC_LYRICS_EN_RATE(기본 2/3), 한국어 = 나머지
  → 기본값이면 영어 50 · 한국어 25 · 연주 25.
  ⚠️ 2026-10-21 대표 결정: 한국어 가사는 두 채널 모두 뺀다("한국어로 부르니 AI 같다").
     MUSIC_LYRICS_KO_ENABLED(기본 off)가 켜져 있을 때만 2) 비율로 한국어가 나온다.
     꺼져 있으면 보컬 영상은 전부 영어 → 영어 75 · 연주 25.
원래 연주인 영상(장소 BGM 장르·연주 format)은 이 모듈을 쓰지 않는다(전부 연주 그대로).
  ✅ 2026-10-29 예외: 발라드·K-시티팝(MUSIC_LYRICS_KO_GENRES)은 항상 한국어 보컬 — "발라드는 한국어도 잘 들린다".
결정값 ko|en|inst 는 곡 메타 language(music_tracks.language·체크포인트·믹스 JSON)에 남는다.
"""

from __future__ import annotations

import math
import os
import random
import re

KO, EN, INST = "ko", "en", "inst"


def _rate(key: str, default: float) -> float:
    try:
        v = float((os.getenv(key) or "").strip() or default)
    except ValueError:
        v = default
    return max(0.0, min(1.0, v))


def instrumental_rate() -> float:
    return _rate("MUSIC_INSTRUMENTAL_RATE", 0.25)


def en_rate() -> float:
    return _rate("MUSIC_LYRICS_EN_RATE", 2 / 3)


def ko_enabled() -> bool:
    """한국어 가사 허용 여부(env MUSIC_LYRICS_KO_ENABLED, 기본 off — 대표 결정 2026-10-21)."""
    return (os.getenv("MUSIC_LYRICS_KO_ENABLED") or "").strip().lower() in ("1", "true", "on", "yes")


def pick_video_language(*, rng: random.Random | None = None) -> str:
    """영상 1개의 언어 ko|en|inst — 연주 rate, 나머지는 영어(한국어 허용 시에만 en_rate 로 갈림)."""
    r = rng or random
    if r.random() < instrumental_rate():
        return INST
    if not ko_enabled():
        return EN
    return EN if r.random() < en_rate() else KO


def ko_genres() -> frozenset[str]:
    """항상 한국어 보컬로 만드는 장르(대표 결정 2026-10-29 "발라드는 한국어로 나와도 잘 들린다").

    env MUSIC_LYRICS_KO_GENRES(쉼표 구분, 기본 "ballad,kcitypop" — K-발라드·K-시티팝). 빈 값("none")이면 예외 없음.
    MUSIC_LYRICS_KO_ENABLED(전체 한국어 허용)와 별개 — 이 장르는 그 스위치가 꺼져 있어도 한국어.
    """
    raw = os.getenv("MUSIC_LYRICS_KO_GENRES")
    raw = "ballad,kcitypop" if raw is None else raw
    return frozenset(g.strip().lower() for g in raw.split(",") if g.strip() and g.strip().lower() != "none")


def assign(n: int, *, rng: random.Random | None = None, lang: str | None = None,
           genre_id: str | None = None) -> list[str]:
    """N곡의 language 목록 — 영상 단위로 통일(전 곡 같은 값). lang 을 주면 그 값(보충 D 용).

    genre_id 가 ko_genres()(기본 발라드)면 연주·영어 없이 전부 한국어 보컬(K-발라드).
    """
    n = max(0, int(n))
    if lang in (KO, EN, INST):
        v = lang
    elif (genre_id or "").strip().lower() in ko_genres():
        v = KO
    else:
        v = pick_video_language(rng=rng)
    return [v] * n


def counts(langs) -> dict[str, int]:
    out = {KO: 0, EN: 0, INST: 0}
    for lang in langs:
        if lang in out:
            out[lang] += 1
    return out


# 곡 제목 금지 패턴 — 앨범 면·트랙 번호처럼 곡 이름이 아닌 것(10/17 where 1번 곡 "A면" 사고).
_BAD_TITLE = re.compile(
    r"(?<![A-Za-z])[ABab]\s*면"            # A면 / B면
    r"|\bside\s*[-:]?\s*[ab12]\b"          # Side A / Side B / side-1
    r"|\btrack\s*(?:no\.?\s*)?\d+"         # Track 1 / Track No.2
    r"|트랙\s*\d+"
    r"|\b(?:intro|outro)\b|인트로|아웃트로"
    r"|\d+\s*번",                          # 1번 / 2 번 곡
    re.IGNORECASE,
)


def is_bad_title(title: str | None) -> bool:
    return bool(_BAD_TITLE.search(title or ""))


TITLE_RULE = (
    "곡 제목 금지: 'A면/B면', 'Side A/B', 'Track 1' 같은 트랙 번호, 'Intro/Outro', '1번' 같은 "
    "번호 표기는 절대 쓰지 말 것 — 제목은 곡의 장면·감정을 담은 이름이어야 한다."
)

_VOCAL_SEG = re.compile(r"vocal|voice|singer|sung|choir|rap\b|a cappella|acapella|harmon(?:y|ies)\b", re.IGNORECASE)


def instrumental_style(style: str | None) -> str:
    """보컬 장르 style → 연주곡 style. 보컬 관련 구절(쉼표 단위)을 빼고 instrumental 을 붙인다."""
    segs = [s.strip() for s in (style or "").split(",")]
    kept = [s for s in segs if s and not _VOCAL_SEG.search(s)]
    if not any(s.lower() == "instrumental" for s in kept):
        kept.append("instrumental")
    return ", ".join(kept)
