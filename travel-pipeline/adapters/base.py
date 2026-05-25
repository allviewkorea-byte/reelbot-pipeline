"""스택 어댑터 추상화.

콘티(이미지) / 영상 생성 모델을 통일된 인터페이스 뒤로 숨겨서
채널 스택 설정(storyboard_model / video_model)에 따라 갈아끼울 수 있게 한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ImageGenerationRequest:
    prompt: str
    reference_images: Optional[list[str]] = None  # 파일 경로 또는 URL
    aspect_ratio: str = "1:1"
    quality: str = "high"
    output_path: Optional[str] = None  # 지정 시 어댑터가 이 경로에 저장
    extra_params: Optional[dict] = None


@dataclass
class ImageGenerationResult:
    image_path: str
    cost_usd: float
    model_used: str
    raw_response: dict
    source_url: Optional[str] = None  # 호스팅 원본 URL(예: WaveSpeed CDN). 로컬 생성이면 None.


class ImageModelAdapter(ABC):
    """모든 콘티/이미지 생성 모델의 통일 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def cost_per_image(self) -> float: ...

    @abstractmethod
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...

    @abstractmethod
    def is_available(self) -> bool:
        """API 키/설정 검증. False면 fallback 대상."""
        ...


@dataclass
class VideoGenerationRequest:
    prompt: str
    reference_images: Optional[list[str]] = None  # front/side/back 또는 콘티 프레임
    character_id: Optional[str] = None  # Kling v2+ 등에서 사용
    aspect_ratio: str = "9:16"
    duration_seconds: int = 5
    output_path: Optional[str] = None  # 지정 시 어댑터가 이 경로에 저장
    extra_params: Optional[dict] = None


@dataclass
class VideoGenerationResult:
    video_path: str
    cost_usd: float
    model_used: str
    character_id_used: Optional[str]
    raw_response: dict


class VideoModelAdapter(ABC):
    """모든 영상 생성 모델의 통일 인터페이스."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supports_character_id(self) -> bool: ...

    @abstractmethod
    async def register_character(
        self, reference_images: list[str], character_name: str
    ) -> Optional[str]:
        """Character ID 발급. 지원 안 하면 None 반환."""
        ...

    @abstractmethod
    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult: ...

    @abstractmethod
    def is_available(self) -> bool: ...
