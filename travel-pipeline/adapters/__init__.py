"""스택 어댑터 패턴: 콘티/영상 생성 모델 추상화."""

from .base import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageModelAdapter,
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoModelAdapter,
)
from .factory import get_image_adapter, get_video_adapter

__all__ = [
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "ImageModelAdapter",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "VideoModelAdapter",
    "get_image_adapter",
    "get_video_adapter",
]
