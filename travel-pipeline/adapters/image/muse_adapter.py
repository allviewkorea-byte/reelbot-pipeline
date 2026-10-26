"""Meta Muse Image (WaveSpeed) 경유 이미지 생성 — 캐릭터 스튜디오·착장 생성용.

API 패턴은 다른 WaveSpeed 어댑터와 동일(kontext_adapter 구조 복제):
  - 제출: POST {BASE}/meta/muse-image/text-to-image  body={"prompt", "aspect_ratio", "output_format"}
          POST {BASE}/meta/muse-image/edit           body={... + "image_urls":[URL ...최대 10]}
  - 폴링: GET  {BASE}/predictions/{task_id}/result
  - 인증: Authorization: Bearer <WAVESPEED_API_KEY>
  - 완료 시 data.status == "completed", data.outputs == [이미지 URL ...]
단가 $0.011/장(두 엔드포인트 동일). size·seed·steps 없음 — 해상도는 aspect_ratio 로 모델이 정한다.

reference_images 가 있으면 edit, 없으면 text-to-image. 참조는 R2 공개 URL 을 그대로 넘긴다
(로컬 경로만 to_data_uri 로 변환 — base64 허용 여부는 미확인이라 호출부는 URL 을 쓴다).

안전 필터: 거부 응답은 wavespeed_ref_video_adapter 의 _BLOCK_RE 로 판정해 RefBlocked 로 올린다
(호출부가 표현을 바꿔 1회 재시도). 제출·폴링 원문은 로그에 남긴다(첫 실호출 파라미터 확인용).
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from ..base import ImageGenerationRequest, ImageGenerationResult, ImageModelAdapter
from ..utils import download_to, to_data_uri
from ..video.wavespeed_ref_video_adapter import _BLOCK_RE, RefBlocked

logger = logging.getLogger(__name__)

T2I_MODEL = "meta/muse-image/text-to-image"
EDIT_MODEL = "meta/muse-image/edit"
MAX_REFS = 10
USD_PER_IMAGE = 0.011
ASPECTS = {"1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "4:5", "5:4"}


def _blocked_or_error(msg: str) -> RuntimeError:
    return RefBlocked(msg) if _BLOCK_RE.search(msg or "") else RuntimeError(msg)


class MuseImageAdapter(ImageModelAdapter):
    BASE_URL = "https://api.wavespeed.ai/api/v3"

    @property
    def name(self) -> str:
        return "meta/muse-image"

    @property
    def cost_per_image(self) -> float:
        return USD_PER_IMAGE

    def is_available(self) -> bool:
        return bool(os.getenv("WAVESPEED_API_KEY"))

    @staticmethod
    def build(request: ImageGenerationRequest) -> tuple[str, dict]:
        """(model_id, payload). 참조가 있으면 edit(최대 10장), 없으면 text-to-image."""
        aspect = request.aspect_ratio if request.aspect_ratio in ASPECTS else "3:4"
        payload: dict = {
            "prompt": request.prompt,
            "aspect_ratio": aspect,
            "output_format": "png",
            "enable_base64_output": False,
            "enable_sync_mode": False,
        }
        refs = list(request.reference_images or [])[:MAX_REFS]
        if refs:
            payload["image_urls"] = [to_data_uri(p) for p in refs]
            return EDIT_MODEL, payload
        return T2I_MODEL, payload

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = os.getenv("WAVESPEED_API_KEY")
        if not api_key:
            raise RuntimeError("WAVESPEED_API_KEY not set")
        if not request.output_path:
            raise ValueError("MuseImageAdapter requires request.output_path")

        headers = {"Authorization": f"Bearer {api_key}"}
        model_id, payload = self.build(request)

        async with httpx.AsyncClient(timeout=180.0) as client:
            submit = await client.post(f"{self.BASE_URL}/{model_id}", headers=headers, json=payload)
            if submit.status_code >= 400:
                logger.error("WaveSpeed Muse submit error: %s - %s", submit.status_code, submit.text[:500])
                raise _blocked_or_error(f"Muse 제출 실패 HTTP {submit.status_code}: {submit.text[:300]}")
            body = submit.json()
            logger.info("[muse] submit %s ok: %s", model_id, str(body)[:300])
            task_id = body["data"]["id"]

            for _ in range(120):  # 최대 ~2분
                await asyncio.sleep(1)
                poll = await client.get(f"{self.BASE_URL}/predictions/{task_id}/result", headers=headers)
                try:
                    poll.raise_for_status()
                except httpx.HTTPStatusError:
                    logger.error("WaveSpeed Muse poll error: %s - %s", poll.status_code, poll.text[:500])
                    raise
                data = poll.json()["data"]
                status = data.get("status")
                if status == "completed":
                    outputs = data.get("outputs") or []
                    if not outputs:
                        raise RuntimeError("Muse completed but no outputs")
                    saved = await download_to(client, outputs[0], request.output_path)
                    return ImageGenerationResult(
                        image_path=saved,
                        cost_usd=self.cost_per_image * len(outputs),
                        model_used=model_id,
                        raw_response=data,
                        source_url=outputs[0],
                    )
                if status == "failed":
                    err = str(data.get("error") or data)
                    logger.warning("[muse] task failed: %s", err[:500])
                    raise _blocked_or_error(f"Muse 생성 실패: {err[:300]}")
            raise TimeoutError("WaveSpeed Muse task timeout")
