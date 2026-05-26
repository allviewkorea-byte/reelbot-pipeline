"""WaveSpeed AI 경유 영상 생성 (Kling v2.1 master).

API 패턴은 WavespeedImageAdapter 와 동일 (submit → poll predictions/result).

WaveSpeed 는 Kling v2.1 master 를 image-to-video / text-to-video 두 변형 경로로
나눠 노출한다. bare 'kwaivgi/kling-v2.1-master' 경로는 존재하지 않아 호출 시
400 을 낸다. reference 이미지 유무에 따라 올바른 변형 경로를 선택한다.

캐릭터 일관성: WaveSpeed Kling 은 별도 character_id 파라미터를 받지 않으므로
(잘못 넘기면 400) reference 이미지를 시작 프레임(image)으로 직접 전달해 유지한다.
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

# WaveSpeed Kling v2.1 master 변형 경로.
_I2V_MODEL_ID = "kwaivgi/kling-v2.1-i2v-master"
_T2V_MODEL_ID = "kwaivgi/kling-v2.1-t2v-master"

# Kling 은 duration(초)·aspect_ratio 를 enum 으로만 받는다. 벗어난 값은 400.
_ALLOWED_DURATIONS = (5, 10)
_ALLOWED_RATIOS = ("16:9", "9:16", "1:1")
_DEFAULT_NEGATIVE_PROMPT = "blur, distort, and low quality"

# 영상 생성 폴링 한도. Kling v3 는 생성에 수 분(최대 ~10분) 걸려
# v1 기준 3분(180회) 한도로는 완료 전에 timeout 이 났다.
_POLL_INTERVAL_SEC = 3
_MAX_WAIT_SEC = 900  # 15분

# WaveSpeed 모델별 초당 대략 단가 (USD). 문서 가격표 기준 추정.
_PRICE_PER_SECOND = {
    _I2V_MODEL_ID: 0.28,
    _T2V_MODEL_ID: 0.28,
}


def _estimate_cost(model_id: str, duration_seconds: int) -> float:
    return _PRICE_PER_SECOND.get(model_id, 0.10) * max(duration_seconds, 1)


def _normalize_duration(seconds: int) -> int:
    """Kling 이 허용하는 duration(5/10초) 중 가장 가까운 값으로 보정."""
    return min(_ALLOWED_DURATIONS, key=lambda d: abs(d - seconds))


class WavespeedVideoAdapter(VideoModelAdapter):
    BASE_URL = "https://api.wavespeed.ai/api/v3"

    def __init__(self, model_id: str = _I2V_MODEL_ID):
        # 레거시로 bare 'kwaivgi/kling-v2.1-master' 가 들어와도 i2v master 로 취급한다.
        self.model_id = model_id if model_id in _PRICE_PER_SECOND else _I2V_MODEL_ID
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
        duration = _normalize_duration(request.duration_seconds)

        # reference 이미지가 있으면 image-to-video, 없으면 text-to-video 변형을 쓴다.
        has_image = bool(request.reference_images)
        model_id = _I2V_MODEL_ID if has_image else _T2V_MODEL_ID

        payload: dict = {
            "prompt": request.prompt,
            "negative_prompt": _DEFAULT_NEGATIVE_PROMPT,
            # Kling 은 duration 을 문자열 enum("5"/"10")으로 받는다.
            "duration": str(duration),
        }
        if has_image:
            # image-to-video: 콘티/캐릭터 reference 를 시작 프레임으로. aspect 는
            # 입력 이미지에서 결정되므로 aspect_ratio 는 보내지 않는다(보내면 400).
            payload["image"] = to_data_uri(request.reference_images[0])
        else:
            # text-to-video: aspect_ratio enum 필요.
            ratio = request.aspect_ratio if request.aspect_ratio in _ALLOWED_RATIOS else "9:16"
            payload["aspect_ratio"] = ratio
        # NOTE: WaveSpeed Kling 은 character_id 파라미터를 받지 않는다(넣으면 400).
        # 캐릭터 일관성은 reference 를 시작 프레임으로 넘기는 방식으로만 유지한다.

        async with httpx.AsyncClient(timeout=300.0) as client:
            submit = await client.post(
                f"{self.BASE_URL}/{model_id}",
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

            for _ in range(_MAX_WAIT_SEC // _POLL_INTERVAL_SEC):
                await asyncio.sleep(_POLL_INTERVAL_SEC)
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
                        cost_usd=_estimate_cost(model_id, duration),
                        model_used=f"wavespeed/{model_id}",
                        character_id_used=request.character_id,
                        raw_response=data,
                    )
                if status == "failed":
                    raise RuntimeError(f"WaveSpeed video task failed: {data.get('error', data)}")
            raise TimeoutError("WaveSpeed video task timeout")
