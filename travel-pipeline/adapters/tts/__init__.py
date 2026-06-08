"""TTS 어댑터 패키지. Supertone 우선, 키 없으면 Edge TTS 폴백."""

from __future__ import annotations

import os

from .base import TTSAdapter


def get_tts_adapter(voice_id: str | None = None) -> TTSAdapter:
    """SUPERTONE_API_KEY + voice_id 가 있으면 Supertone, 없으면 Edge TTS 반환."""
    from .supertone_adapter import SupertoneTTSAdapter

    supertone = SupertoneTTSAdapter(voice_id=voice_id)
    if supertone.is_available():
        return supertone

    if os.getenv("SUPERTONE_API_KEY"):
        # 키는 있는데 voice_id 가 없어 Supertone 을 못 쓰는 경우 원인을 남긴다.
        print(
            "  [tts] SUPERTONE_API_KEY 는 있으나 voice_id 미지정 → Edge TTS 폴백. "
            "SUPERTONE_VOICE_ID 를 설정하거나 요청에 voice_id 를 넘기세요."
        )

    from .edge_adapter import EdgeTTSAdapter

    return EdgeTTSAdapter(voice=voice_id)


__all__ = ["TTSAdapter", "get_tts_adapter"]
