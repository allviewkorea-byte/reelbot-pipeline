"""Edge TTS 경유 TTS (무료 폴백).

SUPERTONE_API_KEY 가 없을 때 자동으로 선택된다. 기존 narration.py 와 동일하게
edge_tts 를 사용한다. Supertone voice_id 가 넘어와도 Edge 보이스 형식이 아니면
기본 한국어 보이스로 합성한다.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from .base import TTSAdapter

_DEFAULT_VOICE = "ko-KR-SunHiNeural"


class EdgeTTSAdapter(TTSAdapter):
    def __init__(self, voice: str | None = None, rate: str = "+0%"):
        # Edge 보이스 이름만 수용(예: ko-KR-SunHiNeural). Supertone voice_id 가
        # 넘어오면 형식이 달라 기본 보이스로 폴백한다.
        self.voice = voice if (voice and "Neural" in voice) else _DEFAULT_VOICE
        self.rate = rate

    @property
    def name(self) -> str:
        return f"edge/{self.voice}"

    @property
    def audio_format(self) -> str:
        return "mp3"

    def is_available(self) -> bool:
        return True  # 무료 폴백 — 항상 사용 가능

    async def _synth(self, text: str, out_path: str) -> None:
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await communicate.save(out_path)

    def synthesize(self, text: str, out_path: str) -> str:
        dest = Path(out_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._synth(text, str(dest)))
        return str(dest)
