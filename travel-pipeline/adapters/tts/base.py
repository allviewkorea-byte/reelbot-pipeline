"""TTS 어댑터 추상화.

나레이션 음성 합성을 통일 인터페이스 뒤로 숨겨 공급자(Supertone/Edge 등)를
갈아끼울 수 있게 한다. 콘티/영상 어댑터와 동일한 교체 가능 구조.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TTSAdapter(ABC):
    """모든 TTS 공급자의 통일 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def audio_format(self) -> str:
        """확장자(점 제외). 예: 'wav' | 'mp3'."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """API 키/설정 검증. False면 폴백 대상."""
        ...

    @abstractmethod
    def synthesize(self, text: str, out_path: str) -> str:
        """text 를 음성으로 합성해 out_path 에 저장하고 경로를 반환."""
        ...
