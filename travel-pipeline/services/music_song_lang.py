"""곡별 가사 언어·연주곡 결정(대표 결정 2026-10-19) — 운동·where 공통.

보컬 영상 1개(N곡)에서
  1) 연주곡 수 = N × MUSIC_INSTRUMENTAL_RATE(기본 0.25) 근처(소수부는 확률로 올림 — 10곡이면 2~3곡),
     위치는 랜덤.
  2) 나머지 곡은 곡마다 독립으로 영어 MUSIC_LYRICS_EN_RATE(기본 0.7) / 한국어 나머지.
원래 연주인 영상(장소 BGM 장르·연주 format)은 이 모듈을 쓰지 않는다(전부 연주 그대로).
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
    return _rate("MUSIC_LYRICS_EN_RATE", 0.7)


def assign(n: int, *, rng: random.Random | None = None) -> list[str]:
    """N곡의 language 목록(곡 순서 그대로). 연주곡 수는 N×비율 근처, 언어는 곡마다 독립."""
    r = rng or random
    n = max(0, int(n))
    exact = n * instrumental_rate()
    k = int(math.floor(exact))
    if r.random() < exact - k:
        k += 1
    inst_pos = set(r.sample(range(n), min(n, k)))
    p_en = en_rate()
    return [INST if i in inst_pos else (EN if r.random() < p_en else KO) for i in range(n)]


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
