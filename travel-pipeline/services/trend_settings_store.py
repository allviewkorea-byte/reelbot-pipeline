"""채널별 트렌드 자동 분석 설정 저장소.

스케줄러가 어떤 채널을 분석할지 결정할 때 참조한다.
저장 위치: travel-pipeline/data/trend_settings/{channel_id}.json
"""

from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "trend_settings"

_DEFAULTS = {
    "enabled": False,
    "keywords": [],
    "categories": [],
    "formats": ["shorts", "long"],
    "schedule": "daily",
    "lastAnalyzedAt": None,
}


def _path(channel_id: str) -> Path:
    safe = channel_id.replace("/", "_")
    return _SETTINGS_DIR / f"{safe}.json"


def get_settings(channel_id: str) -> dict:
    path = _path(channel_id)
    if not path.exists():
        return {**_DEFAULTS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**_DEFAULTS}
    return {**_DEFAULTS, **data}


def save_settings(channel_id: str, settings: dict) -> dict:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    merged = {**_DEFAULTS, **get_settings(channel_id), **settings}
    _path(channel_id).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged


def all_settings() -> list[dict]:
    """모든 채널의 설정을 (channel_id 포함) 반환한다."""
    if not _SETTINGS_DIR.exists():
        return []
    out: list[dict] = []
    for path in _SETTINGS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data.setdefault("channelId", path.stem)
        out.append({**_DEFAULTS, **data})
    return out


def touch_last_analyzed(channel_id: str, iso_ts: str) -> None:
    save_settings(channel_id, {"lastAnalyzedAt": iso_ts})
