"""ElevenLabs Sound Effects(text-to-sound-effects) — 쇼츠 사운드 디자인용 효과음 생성.

POST https://api.elevenlabs.io/v1/sound-generation  (헤더 xi-api-key = 기존 ELEVENLABS_API_KEY)
body: text(필수), duration_seconds(0.5~30, 지정 시 초당 11크레딧), prompt_influence(0~1, 기본 0.3),
      model_id(eleven_text_to_sound_v2). 응답 = 오디오 바이트(mp3).
유료 플랜 생성물은 출처 표기 없이 상업 이용 가능(ElevenLabs sound-effects/commercial).
저작권 있는 효과음 라이브러리는 쓰지 않는다 — 효과음은 전부 여기서 새로 생성한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

URL = "https://api.elevenlabs.io/v1/sound-generation"
MODEL = os.getenv("SHORTS_SFX_MODEL", "eleven_text_to_sound_v2")
CREDITS_PER_SEC = 11


def is_available() -> bool:
    return bool(os.getenv("ELEVENLABS_API_KEY"))


def generate(text: str, seconds: float, dest: Path, *, prompt_influence: float = 0.5,
             client: httpx.Client | None = None) -> dict:
    """효과음 1개 → dest(mp3). 반환 {path, seconds, credits}. 실패 시 RuntimeError."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY 미설정 — 효과음을 만들 수 없습니다.")
    sec = round(min(30.0, max(0.5, seconds)), 2)
    body = {"text": text, "duration_seconds": sec, "prompt_influence": prompt_influence, "model_id": MODEL}
    own = client is None
    client = client or httpx.Client(timeout=120.0)
    try:
        r = client.post(URL, headers={"xi-api-key": key, "Content-Type": "application/json"}, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs 효과음 실패 {r.status_code}: {r.text[:300]}")
        dest.write_bytes(r.content)
    finally:
        if own:
            client.close()
    return {"path": str(dest), "seconds": sec, "credits": int(round(sec * CREDITS_PER_SEC))}
