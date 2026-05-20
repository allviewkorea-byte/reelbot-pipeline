"""채널 스택 설정(storyboard_model / video_model)에 따라 어댑터 인스턴스화.

키가 없으면 자동으로 기존 모델(gpt-image-1 / Kling v1)로 fallback.
WaveSpeed 어댑터는 해당 모델을 선택했을 때만 지연 import 한다.
"""

from __future__ import annotations

from .base import ImageModelAdapter, VideoModelAdapter
from .image.gpt_image_adapter import GptImageAdapter
from .video.kling_v1_adapter import KlingV1Adapter


def get_image_adapter(model: str = "default") -> ImageModelAdapter:
    """storyboard_model 값에 따라 이미지 어댑터 반환.
    값: 'default' / 'gpt-image-1' / 'z-image-turbo'. 키 없으면 fallback."""
    if model == "z-image-turbo":
        from .image.wavespeed_image_adapter import WavespeedImageAdapter

        adapter = WavespeedImageAdapter(model_id="wavespeed-ai/z-image-turbo")
        if adapter.is_available():
            return adapter
        # WAVESPEED_API_KEY 없으면 fallback
    return GptImageAdapter()


def get_video_adapter(model: str = "default") -> VideoModelAdapter:
    """video_model 값에 따라 영상 어댑터 반환.
    값: 'default' / 'kling-v1' / 'kling-v3'. 키 없으면 fallback."""
    if model == "kling-v3":
        from .video.wavespeed_video_adapter import WavespeedVideoAdapter

        # WaveSpeed 의 최신 Kling 마스터 모델. (v3 실제 model ID는 WaveSpeed 문서 기준 갱신)
        adapter = WavespeedVideoAdapter(model_id="kwaivgi/kling-v2.1-master")
        if adapter.is_available():
            return adapter
    return KlingV1Adapter()
