"""TTS 어댑터 패키지.

프로바이더 선택은 환경변수 TTS_PROVIDER("supertone"|"elevenlabs"|"edge")로 한다.
미설정(기본)이면 기존 동작 — Supertone 우선, 키 없으면 Edge 폴백.
선택한 프로바이더가 사용 불가하면 Edge 로 graceful 폴백(파이프라인 안 멈춤).
"""

from __future__ import annotations

import os

from .base import TTSAdapter


def get_tts_adapter(voice_id: str | None = None) -> TTSAdapter:
    """TTS_PROVIDER 환경변수로 어댑터 선택. 미설정이면 Supertone→Edge(기존 동작)."""
    provider = (os.getenv("TTS_PROVIDER") or "").strip().lower()

    def _edge() -> TTSAdapter:
        from .edge_adapter import EdgeTTSAdapter

        return EdgeTTSAdapter(voice=voice_id)

    if provider == "edge":
        return _edge()

    if provider == "elevenlabs":
        from .elevenlabs_adapter import ElevenLabsTTSAdapter

        el = ElevenLabsTTSAdapter(voice_id=voice_id)
        if el.is_available():
            return el
        print(
            "  [tts] TTS_PROVIDER=elevenlabs 인데 ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID "
            "미설정 → Edge TTS 폴백."
        )
        return _edge()

    # provider 미설정(기본) 또는 "supertone": Supertone 우선, 없으면 Edge (기존 동작 유지).
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

    return _edge()


__all__ = ["TTSAdapter", "get_tts_adapter"]
