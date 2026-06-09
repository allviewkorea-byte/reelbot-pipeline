"""Supertone API 경유 TTS (한국어 자연도 최상).

API (docs.supertoneapi.com):
  - POST https://supertoneapi.com/v1/text-to-speech/{voice_id}
  - 헤더: x-sup-api-key: <SUPERTONE_API_KEY>, Content-Type: application/json
  - body: {"text", "language", "style"?, "model", "output_format"}
  - 응답: 바이너리 오디오(Content-Type audio/wav | audio/mpeg)

voice_id 는 요청값 → SUPERTONE_VOICE_ID 환경변수 순으로 결정한다. 키와 voice_id 가
모두 있어야 사용 가능(없으면 Edge TTS 로 폴백).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

from .base import TTSAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://supertoneapi.com/v1/text-to-speech"
_MODEL = "sona_speech_1"


class SupertoneTTSAdapter(TTSAdapter):
    def __init__(self, voice_id: str | None = None, language: str = "ko", style: str = ""):
        self.voice_id = voice_id or os.getenv("SUPERTONE_VOICE_ID", "")
        self.language = language
        self.style = style

    @property
    def name(self) -> str:
        return f"supertone/{_MODEL}"

    @property
    def audio_format(self) -> str:
        return "wav"

    def is_available(self) -> bool:
        return bool(os.getenv("SUPERTONE_API_KEY") and self.voice_id)

    def synthesize(self, text: str, out_path: str) -> str:
        api_key = os.getenv("SUPERTONE_API_KEY")
        if not api_key:
            raise RuntimeError("SUPERTONE_API_KEY not set")
        if not self.voice_id:
            raise RuntimeError("Supertone voice_id 미지정 (SUPERTONE_VOICE_ID 또는 요청값 필요)")

        payload: dict = {
            "text": text,
            "language": self.language,
            "model": _MODEL,
            "output_format": "wav",
        }
        if self.style:
            payload["style"] = self.style

        headers = {"x-sup-api-key": api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{_BASE_URL}/{self.voice_id}", headers=headers, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error("Supertone TTS error: %s - %s", resp.status_code, resp.text[:500])
                raise

        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return str(dest)
