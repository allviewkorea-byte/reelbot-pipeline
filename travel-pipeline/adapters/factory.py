"""채널 스택 설정(storyboard_model / video_model)에 따라 어댑터 인스턴스화.

콘티는 WaveSpeed 스케치 단일 모델. 영상은 모델 값에 따라 선택하고,
키가 없으면 기존 모델(Kling v1)로 fallback 한다.
WaveSpeed 어댑터는 지연 import 한다.
"""

from __future__ import annotations

from .base import ImageModelAdapter, VideoModelAdapter
from .image.gpt_image_adapter import GptImageAdapter
from .video.kling_v1_adapter import KlingV1Adapter


def get_image_adapter(model: str = "default") -> ImageModelAdapter:
    """콘티 이미지 어댑터 반환.

    콘티는 WaveSpeed 스케치(z-image/turbo) 단일 모델이다. storyboard_model 값
    ('sketch' / 'default' / 과거 채널에 저장된 'z-image-turbo'·'gpt-image-1')과
    무관하게 동일하게 처리한다. WAVESPEED_API_KEY 가 없을 때만 gpt-image 로
    fallback 한다(사용자 선택 옵션 아님, 안전망)."""
    from .image.wavespeed_image_adapter import WavespeedImageAdapter

    adapter = WavespeedImageAdapter(model_id="wavespeed-ai/z-image/turbo")
    if adapter.is_available():
        return adapter
    # WAVESPEED_API_KEY 없으면 gpt-image 로 fallback
    return GptImageAdapter()


def get_video_adapter(model: str = "default") -> VideoModelAdapter:
    """video_model 값에 따라 영상 어댑터 반환.
    값: 'default' / 'kling-v1' / 'kling-v3'. 키 없으면 fallback."""
    if model == "kling-v3":
        from .video.wavespeed_video_adapter import WavespeedVideoAdapter

        # WaveSpeed 의 최신 Kling 마스터 모델. 어댑터가 reference 유무로 i2v/t2v
        # 변형 경로를 자동 선택한다(bare 'kling-v2.1-master' 경로는 400).
        adapter = WavespeedVideoAdapter(model_id="kwaivgi/kling-v2.1-i2v-master")
        if adapter.is_available():
            print(f"  [adapter] 영상 모델: {adapter.name} (Kling v3, WaveSpeed)")
            return adapter
        # kling-v3 을 선택했는데 WAVESPEED_API_KEY 가 없으면 조용히 v1 으로 떨어져
        # "Kling v3 설정했는데 v1 으로 동작" 증상이 된다. 원인이 보이도록 경고를 남긴다.
        print(
            "  [adapter] ⚠ video_model='kling-v3' 인데 WAVESPEED_API_KEY 가 없어 "
            "Kling v1 으로 폴백합니다. Railway 환경변수에 WAVESPEED_API_KEY 를 설정하세요."
        )
    return KlingV1Adapter()
