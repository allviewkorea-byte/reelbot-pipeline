"""WaveSpeed AI 경유 이미지 생성 (Z-Image Turbo 등).

API 패턴 (https://wavespeed.ai/docs):
  - 제출: POST {BASE}/{model_id}  body={"prompt", "size", ...}
  - 폴링: GET  {BASE}/predictions/{task_id}/result
  - 인증: Authorization: Bearer <WAVESPEED_API_KEY>
  - 완료 시 data.status == "completed", data.outputs[0] == 이미지 URL

콘티는 스케치 톤이라 캐릭터 일관성이 불필요하고 비용도 늘어나므로
reference_images 는 의도적으로 전달하지 않는다 (text-to-image).
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from ..base import ImageGenerationRequest, ImageGenerationResult, ImageModelAdapter
from ..utils import download_to

logger = logging.getLogger(__name__)

_ASPECT_TO_SIZE = {
    "1:1": "1024*1024",
    "9:16": "1024*1536",
    "16:9": "1536*1024",
}


class WavespeedImageAdapter(ImageModelAdapter):
    BASE_URL = "https://api.wavespeed.ai/api/v3"

    def __init__(self, model_id: str = "wavespeed-ai/z-image/turbo"):
        self.model_id = model_id

    @property
    def name(self) -> str:
        return self.model_id

    @property
    def cost_per_image(self) -> float:
        prices = {
            "wavespeed-ai/z-image/turbo": 0.01,
            "wavespeed-ai/nano-banana-2": 0.013,
            "wavespeed-ai/seedream-v5-lite": 0.032,
        }
        return prices.get(self.model_id, 0.05)

    def is_available(self) -> bool:
        return bool(os.getenv("WAVESPEED_API_KEY"))

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = os.getenv("WAVESPEED_API_KEY")
        if not api_key:
            raise RuntimeError("WAVESPEED_API_KEY not set")
        if not request.output_path:
            raise ValueError("WavespeedImageAdapter requires request.output_path")

        headers = {"Authorization": f"Bearer {api_key}"}
        size = _ASPECT_TO_SIZE.get(request.aspect_ratio, "1024*1024")
        # 공식 docs(z-image/turbo) request body 형식.
        payload = {
            "prompt": request.prompt,
            "size": size,
            "seed": -1,
            "output_format": "jpeg",
            "enable_sync_mode": False,
            "enable_base64_output": False,
            **(request.extra_params or {}),
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            submit = await client.post(
                f"{self.BASE_URL}/{self.model_id}",
                headers=headers,
                json=payload,
            )
            try:
                submit.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error(
                    "WaveSpeed image submit error: %s - %s",
                    submit.status_code,
                    submit.text,
                )
                raise
            task_id = submit.json()["data"]["id"]

            for _ in range(60):  # max ~60s (Z-Image Turbo는 보통 3-5초)
                await asyncio.sleep(1)
                poll = await client.get(
                    f"{self.BASE_URL}/predictions/{task_id}/result",
                    headers=headers,
                )
                try:
                    poll.raise_for_status()
                except httpx.HTTPStatusError:
                    logger.error(
                        "WaveSpeed image poll error: %s - %s",
                        poll.status_code,
                        poll.text,
                    )
                    raise
                data = poll.json()["data"]
                status = data.get("status")
                if status == "completed":
                    image_url = data["outputs"][0]
                    # CDN URL을 로컬에도 저장(영상 생성 단계 reference용)하되,
                    # 브라우저 미리보기는 외부 접근 가능한 CDN URL을 직접 쓰도록 함께 반환.
                    saved = await download_to(client, image_url, request.output_path)
                    return ImageGenerationResult(
                        image_path=saved,
                        cost_usd=self.cost_per_image,
                        model_used=self.name,
                        raw_response=data,
                        source_url=image_url,
                    )
                if status == "failed":
                    raise RuntimeError(f"WaveSpeed task failed: {data.get('error', data)}")
            raise TimeoutError("WaveSpeed image task timeout")
