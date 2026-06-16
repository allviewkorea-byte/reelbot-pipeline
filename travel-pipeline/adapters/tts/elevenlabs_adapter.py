"""ElevenLabs API 경유 TTS.

API:
  - POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
  - 헤더: xi-api-key: <ELEVENLABS_API_KEY>, Content-Type: application/json,
          Accept: audio/mpeg
  - body: {"text", "model_id", "voice_settings"}
  - 응답: 바이너리 오디오(audio/mpeg, mp3)

키·voice_id·model_id 는 전부 환경변수(하드코딩 금지):
  ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID(기본 eleven_multilingual_v2).
키와 voice_id 가 모두 있어야 사용 가능(없으면 상위에서 다른 프로바이더로 폴백).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

from .base import TTSAdapter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
_DEFAULT_MODEL = "eleven_multilingual_v2"


class ElevenLabsTTSAdapter(TTSAdapter):
    def __init__(self, voice_id: str | None = None):
        # 앞뒤 공백/줄바꿈 제거(대시보드 환경변수에 섞이는 경우가 잦아 401 유발).
        self.voice_id = (voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")).strip()
        self.model_id = os.getenv("ELEVENLABS_MODEL_ID", _DEFAULT_MODEL).strip()

    @property
    def name(self) -> str:
        return f"elevenlabs/{self.model_id}"

    @property
    def audio_format(self) -> str:
        return "mp3"

    def is_available(self) -> bool:
        return bool(os.getenv("ELEVENLABS_API_KEY") and self.voice_id)

    def synthesize(self, text: str, out_path: str) -> str:
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        # 키 앞뒤 공백/줄바꿈 제거 — 401 의 흔한 원인.
        api_key = api_key.strip()
        if not self.voice_id:
            raise RuntimeError("ElevenLabs voice_id 미지정 (ELEVENLABS_VOICE_ID 필요)")

        # 진단 로그(비밀값 노출 금지: 존재 여부·길이·앞 3글자만). stdout 로 남겨 Railway 에서 확인.
        print(
            f"  [tts:elevenlabs] ELEVENLABS_API_KEY present={bool(api_key)} "
            f"len={len(api_key)} prefix={api_key[:3]!r} | "
            f"model_id={self.model_id!r} voice_id={self.voice_id!r}"
        )

        # stability 만 env 화(기본 0.5=현재). 0.6~0.7 로 올리면 라인 간 음색 흔들림↓.
        try:
            stability = float(os.getenv("SAYEON_TTS_STABILITY") or "0.5")
        except ValueError:
            stability = 0.5
        stability = min(1.0, max(0.0, stability))
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{_BASE_URL}/{self.voice_id}", headers=headers, json=payload
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error(
                    "ElevenLabs TTS error: %s - %s", resp.status_code, resp.text[:500]
                )
                raise

        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return str(dest)
