"""기존 Kling v1 영상 생성(KIE 경유)을 어댑터로 wrap.

kie_client.generate_kie_clip 의 기존 동작을 그대로 호출한다.
Character ID 미지원 — reference_images[0](콘티 프레임)만 start image로 사용.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from ..base import VideoGenerationRequest, VideoGenerationResult, VideoModelAdapter


class KlingV1Adapter(VideoModelAdapter):
    @property
    def name(self) -> str:
        return "kling-v1"

    @property
    def supports_character_id(self) -> bool:
        return False

    def is_available(self) -> bool:
        # 기존 KIE 경로: Access/Secret 키 또는 단일 키 중 하나라도 있으면 사용 가능.
        return bool(
            os.getenv("KIE_ACCESS_KEY") and os.getenv("KIE_SECRET_KEY")
        ) or bool(os.getenv("KIE_API_KEY"))

    async def register_character(self, reference_images, character_name) -> Optional[str]:
        return None  # v1은 Character ID 미지원

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        from config import Config
        from kie_client import generate_kie_clip

        if not request.output_path:
            raise ValueError("KlingV1Adapter requires request.output_path")

        ref_image = None
        if request.reference_images:
            first = Path(request.reference_images[0])
            if first.exists():
                ref_image = first

        scene = {
            "prompt_en": request.prompt,
            "duration_sec": request.duration_seconds,
        }
        dest = Path(request.output_path)
        config = Config()

        # generate_kie_clip 은 동기(requests 기반)라 스레드로 위임.
        clip_path = await asyncio.to_thread(
            generate_kie_clip, scene, ref_image, dest, config
        )

        return VideoGenerationResult(
            video_path=str(clip_path),
            cost_usd=0.0,  # 기존 v1 경로는 별도 비용 추정 없음
            model_used=self.name,
            character_id_used=None,
            raw_response={},
        )
