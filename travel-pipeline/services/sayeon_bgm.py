"""사연 트랙 — BGM 자동 선택 (PR-BGM).

사연 톤/감정에 맞는 분위기(mood)를 고르고, R2 의 bgm/{mood}/ 폴더에서 한 곡을
무작위로 내려받아 합성 단계(sayeon_assemble)가 나레이션 아래에 덕킹해 깔 수 있게 한다.

분위기 매핑(작업지시서):
  serious / sadness / anxiety  → emotional
  shock / anger                → suspense
  joy / flutter / hopeful 결말  → hopeful

R2 미설정·해당 분위기 곡 없음·다운로드 실패는 치명적이지 않다 — None 을 돌려주고
합성은 BGM 없이 계속 진행한다(파이프라인을 멈추지 않음).
"""

from __future__ import annotations

import logging
import os
import random
from collections import Counter
from pathlib import Path

from adapters import r2_storage
from services.sayeon_character import normalize_tone

logger = logging.getLogger(__name__)

# 지원 분위기(= R2 bgm/ 하위 폴더명).
VALID_MOODS = ("emotional", "suspense", "hopeful")
DEFAULT_MOOD = "emotional"

# 감정(부록 D 7종) → 분위기.
_MOOD_BY_EMOTION = {
    "sadness": "emotional",
    "anxiety": "emotional",
    "deadpan": "emotional",
    "shock": "suspense",
    "anger": "suspense",
    "joy": "hopeful",
    "flutter": "hopeful",
}


def select_mood(tone: str = "light", emotions: list[str] | None = None) -> str:
    """톤 + 씬 감정 분포 → 영상 전체에 깔 BGM 분위기 1개.

    - serious 톤은 emotional 쪽에 가중(작업지시서: serious → emotional).
    - 결말(마지막 씬)이 긍정(joy/flutter=hopeful)이면 hopeful 에 가중("hopeful 결말").
    - 신호가 전혀 없으면 DEFAULT_MOOD.
    """
    emotions = emotions or []
    counts: Counter[str] = Counter()
    for e in emotions:
        mood = _MOOD_BY_EMOTION.get((e or "").strip().lower())
        if mood:
            counts[mood] += 1
    if normalize_tone(tone) == "serious":
        counts["emotional"] += 2
    if emotions:
        last = _MOOD_BY_EMOTION.get((emotions[-1] or "").strip().lower())
        if last == "hopeful":
            counts["hopeful"] += 2  # 긍정적 결말은 hopeful 로 마무리
    if not counts:
        return DEFAULT_MOOD
    return counts.most_common(1)[0][0]


def fetch_bgm(mood: str, out_dir: str | Path) -> Path | None:
    """R2 bgm/{mood}/ 에서 무작위 1곡을 out_dir 로 내려받아 경로 반환(없으면 None).

    같은 분위기 안에서 매번 다른 곡이 깔리도록 무작위로 고른다.
    """
    if mood not in VALID_MOODS:
        logger.warning("알 수 없는 BGM 분위기 '%s' — DEFAULT_MOOD 로 대체", mood)
        mood = DEFAULT_MOOD
    if not r2_storage.is_available():
        logger.warning("R2 미설정 — BGM 없이 진행합니다.")
        return None
    try:
        keys = r2_storage.list_bgm_keys(mood)
    except Exception as e:  # noqa: BLE001
        logger.warning("BGM 목록 조회 실패(mood=%s) — BGM 없이 진행: %s", mood, e)
        return None
    if not keys:
        logger.warning("BGM 없음(bgm/%s/ 비어 있음) — BGM 없이 진행합니다.", mood)
        return None

    key = random.choice(keys)
    ext = os.path.splitext(key)[1].lower() or ".mp3"
    dest = Path(out_dir) / f"bgm{ext}"
    try:
        r2_storage.download_bgm(key, str(dest))
    except Exception as e:  # noqa: BLE001
        logger.warning("BGM 다운로드 실패(%s) — BGM 없이 진행: %s", key, e)
        return None
    logger.info("BGM 선택: mood=%s key=%s", mood, key)
    return dest
