"""FLUX.1 Kontext Pro Multi (WaveSpeed) 경유 씬 이미지 생성.

사연 트랙 캐릭터 일관성 엔진. 캐릭터 시트(reference)를 in-context 로 넣어
정체성·웹툰 스타일을 유지한 채 새 장면을 생성한다(spike 로 검증된 방식).

API 패턴은 다른 WaveSpeed 어댑터와 동일:
  - 제출: POST {BASE}/wavespeed-ai/flux-kontext-pro/multi
          body={"prompt", "images":[URL ...최대 5], "aspect_ratio", "num_images", "seed"}
  - 폴링: GET  {BASE}/predictions/{task_id}/result
  - 인증: Authorization: Bearer <WAVESPEED_API_KEY>
  - 완료 시 data.status == "completed", data.outputs == [이미지 URL ...]

reference_images 는 캐릭터 시트 R2 공개 URL 을 그대로 넘긴다(to_data_uri 가
http URL 은 그대로, 로컬 경로는 base64 data URI 로 변환).

큐레이션: extra_params['num_images'] 로 씬당 후보를 여러 장 받는다. generate() 는
인터페이스대로 첫 장을 output_path 에 저장해 반환하되, 전체 후보 URL 은
raw_response['outputs'] 로 노출한다(호출부가 베스트 선택).
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from ..base import ImageGenerationRequest, ImageGenerationResult, ImageModelAdapter
from ..utils import download_to, to_data_uri

logger = logging.getLogger(__name__)


class KontextImageAdapter(ImageModelAdapter):
    BASE_URL = "https://api.wavespeed.ai/api/v3"

    def __init__(self, model_id: str = "wavespeed-ai/flux-kontext-pro/multi"):
        self.model_id = model_id

    @property
    def name(self) -> str:
        return self.model_id

    @property
    def cost_per_image(self) -> float:
        # WaveSpeed Kontext Pro 대략 단가(USD/장). 정확값은 가격표 확인 필요(추정).
        return 0.04

    def is_available(self) -> bool:
        return bool(os.getenv("WAVESPEED_API_KEY"))

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = os.getenv("WAVESPEED_API_KEY")
        if not api_key:
            raise RuntimeError("WAVESPEED_API_KEY not set")
        if not request.output_path:
            raise ValueError("KontextImageAdapter requires request.output_path")
        if not request.reference_images:
            raise ValueError(
                "KontextImageAdapter requires reference_images (캐릭터 시트)"
            )

        headers = {"Authorization": f"Bearer {api_key}"}
        extra = request.extra_params or {}
        # 시트 reference 는 최대 5장. http URL 은 그대로, 로컬은 data URI 로.
        images = [to_data_uri(p) for p in request.reference_images[:5]]
        payload = {
            "prompt": request.prompt,
            "images": images,
            "aspect_ratio": request.aspect_ratio or "9:16",
            "num_images": int(extra.get("num_images", 1)),
            "output_format": "png",
            "enable_base64_output": False,
            "enable_sync_mode": False,
        }
        if "seed" in extra and extra["seed"] is not None and int(extra["seed"]) >= 0:
            payload["seed"] = int(extra["seed"])

        async with httpx.AsyncClient(timeout=180.0) as client:
            submit = await client.post(
                f"{self.BASE_URL}/{self.model_id}",
                headers=headers,
                json=payload,
            )
            try:
                submit.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error(
                    "WaveSpeed Kontext submit error: %s - %s",
                    submit.status_code,
                    submit.text,
                )
                raise
            task_id = submit.json()["data"]["id"]

            for _ in range(120):  # 최대 ~2분 (Kontext 는 보통 수 초)
                await asyncio.sleep(1)
                poll = await client.get(
                    f"{self.BASE_URL}/predictions/{task_id}/result",
                    headers=headers,
                )
                try:
                    poll.raise_for_status()
                except httpx.HTTPStatusError:
                    logger.error(
                        "WaveSpeed Kontext poll error: %s - %s",
                        poll.status_code,
                        poll.text,
                    )
                    raise
                data = poll.json()["data"]
                status = data.get("status")
                if status == "completed":
                    outputs = data.get("outputs") or []
                    if not outputs:
                        raise RuntimeError("Kontext completed but no outputs")
                    # 인터페이스대로 첫 후보를 output_path 에 저장. 전체 후보는
                    # raw_response['outputs'] 로 호출부에 노출(큐레이션).
                    saved = await download_to(client, outputs[0], request.output_path)
                    return ImageGenerationResult(
                        image_path=saved,
                        cost_usd=self.cost_per_image * len(outputs),
                        model_used=self.name,
                        raw_response=data,
                        source_url=outputs[0],
                    )
                if status == "failed":
                    raise RuntimeError(
                        f"WaveSpeed Kontext task failed: {data.get('error', data)}"
                    )
            raise TimeoutError("WaveSpeed Kontext task timeout")
