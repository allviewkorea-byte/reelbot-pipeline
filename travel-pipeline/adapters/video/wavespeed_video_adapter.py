"""WaveSpeed AI 경유 영상 생성 (Kling v2.1+ 등).

API 패턴은 WavespeedImageAdapter 와 동일 (submit → poll predictions/result).
캐릭터 일관성: WaveSpeed 가 별도 Character ID 등록을 노출하지 않으므로
3면 reference 이미지를 start image 로 직접 전달하는 방식으로 동작한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

from ..base import VideoGenerationRequest, VideoGenerationResult, VideoModelAdapter
from ..utils import download_to, to_data_uri

logger = logging.getLogger(__name__)

# WaveSpeed 모델별 초당 대략 단가 (USD). 문서 가격표 기준 추정.
_PRICE_PER_SECOND = {
    "kwaivgi/kling-v2.1-master": 0.28,
}


def _estimate_cost(model_id: str, duration_seconds: int) -> float:
    return _PRICE_PER_SECOND.get(model_id, 0.10) * max(duration_seconds, 1)


class WavespeedVideoAdapter(VideoModelAdapter):
    BASE_URL = "https://api.wavespeed.ai/api/v3"

    def __init__(self, model_id: str = "kwaivgi/kling-v2.1-master"):
        self.model_id = model_id
        self._character_cache: dict[str, str] = {}

    @property
    def name(self) -> str:
        return f"wavespeed/{self.model_id}"

    @property
    def supports_character_id(self) -> bool:
        return "kling" in self.model_id  # Kling v2+ 만 지원

    def is_available(self) -> bool:
        return bool(os.getenv("WAVESPEED_API_KEY"))

    async def register_character(self, reference_images, character_name) -> Optional[str]:
        """WaveSpeed 는 현재 별도 Character ID 등록을 노출하지 않는다.
        매 호출마다 reference 를 직접 전달하는 방식으로 fallback (None 반환)."""
        return None

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        api_key = os.getenv("WAVESPEED_API_KEY")
        if not api_key:
            raise RuntimeError("WAVESPEED_API_KEY not set")
        if not request.output_path:
            raise ValueError("WavespeedVideoAdapter requires request.output_path")

        headers = {"Authorization": f"Bearer {api_key}"}
        payload: dict = {
            "prompt": request.prompt,
            "duration": request.duration_seconds,
            "aspect_ratio": request.aspect_ratio,
        }
        if request.reference_images:
            # Kling image-to-video: 첫 reference 를 start image 로 사용.
            payload["image"] = to_data_uri(request.reference_images[0])
        if request.character_id:
            payload["character_id"] = request.character_id

        async with httpx.AsyncClient(timeout=300.0) as client:
            submit = await client.post(
                f"{self.BASE_URL}/{self.model_id}",
                headers=headers,
                json=payload,
            )
            try:
                submit.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error(
                    "WaveSpeed video submit error: %s - %s",
                    submit.status_code,
                    submit.text,
                )
                raise
            task_id = submit.json()["data"]["id"]

            for _ in range(180):  # max ~3min (Kling 영상 생성)
                await asyncio.sleep(1)
                poll = await client.get(
                    f"{self.BASE_URL}/predictions/{task_id}/result",
                    headers=headers,
                )
                try:
                    poll.raise_for_status()
                except httpx.HTTPStatusError:
                    logger.error(
                        "WaveSpeed video poll error: %s - %s",
                        poll.status_code,
                        poll.text,
                    )
                    raise
                data = poll.json()["data"]
                status = data.get("status")
                if status == "completed":
                    video_url = data["outputs"][0]
                    saved = await download_to(client, video_url, request.output_path)
                    return VideoGenerationResult(
                        video_path=saved,
                        cost_usd=_estimate_cost(self.model_id, request.duration_seconds),
                        model_used=self.name,
                        character_id_used=request.character_id,
                        raw_response=data,
                    )
                if status == "failed":
                    raise RuntimeError(f"WaveSpeed video task failed: {data.get('error', data)}")
            raise TimeoutError("WaveSpeed video task timeout")
