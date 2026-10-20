"""WaveSpeed 레퍼런스 영상(reference-to-video) — Kling O3 Reference(주력) · Seedance(비교용) 공용.

공식 문서(WaveSpeed docs, kwaivgi-kling-video-o3-pro-reference-to-video):
  POST {BASE}/kwaivgi/kling-video-o3-pro/reference-to-video
  body: prompt(필수), images(최대 7장 — 영상 레퍼런스 없을 때), duration(3~15초, 기본 5),
        aspect_ratio(16:9|9:16|1:1), sound(AI 오디오, 기본 off)
  가격: $1.20 / 5초(= $0.24/초). 영상 레퍼런스 ×1.5, sound ×1.25.
폴링은 기존 어댑터와 같은 predictions/{id}/result.

모델 ID·초당 단가는 env 로 바꿀 수 있다(SHORTS_KLING_MODEL / SHORTS_KLING_USD_PER_SEC,
SHORTS_SEEDANCE_MODEL / SHORTS_SEEDANCE_USD_PER_SEC). Seedance 의 WaveSpeed 레퍼런스 경로·필드는
공식 문서로 확인하지 못해(미확인) 비교 1회 결과에 응답 원문을 그대로 남긴다.

레퍼런스가 정책(얼굴·미성년자·민감 콘텐츠)으로 거부되면 RefBlocked — 호출부가 아기 없는 대본으로
대체하는 등 분기한다. 그 외 실패는 RuntimeError.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.wavespeed.ai/api/v3"
KLING_MODEL = os.getenv("SHORTS_KLING_MODEL", "kwaivgi/kling-video-o3-pro/reference-to-video")
KLING_USD_PER_SEC = float(os.getenv("SHORTS_KLING_USD_PER_SEC", "0.24"))
SEEDANCE_MODEL = os.getenv("SHORTS_SEEDANCE_MODEL", "bytedance/seedance-2.5/reference-to-video")
SEEDANCE_USD_PER_SEC = float(os.getenv("SHORTS_SEEDANCE_USD_PER_SEC", "0") or 0)
MAX_IMAGES = 7
_POLL_SEC = 4
_MAX_WAIT_SEC = 1800

# 정책 거부로 보는 응답 문구(모델·제공처마다 다름 — 넓게 잡고 원문은 로그·결과에 남긴다).
_BLOCK_RE = re.compile(
    r"real\s*human|human\s*face|face|minor|child|kid|underage|sensitive|moderat|policy|"
    r"safety|nsfw|violat|inappropriate|not\s*allowed|prohibit|reject|flagged", re.I)


class RefBlocked(RuntimeError):
    """레퍼런스·프롬프트가 정책으로 거부됨(재시도해도 같은 결과)."""


@dataclass
class RefVideoResult:
    url: str
    seconds: int
    cost_usd: float
    model: str
    task_id: str


class WavespeedRefVideoAdapter:
    def __init__(self, model_id: str = KLING_MODEL, usd_per_sec: float = KLING_USD_PER_SEC):
        self.model_id = model_id
        self.usd_per_sec = usd_per_sec

    @staticmethod
    def is_available() -> bool:
        return bool(os.getenv("WAVESPEED_API_KEY"))

    def payload(self, prompt: str, images: list[str], seconds: int, aspect_ratio: str = "9:16") -> dict:
        return {
            "prompt": prompt,
            "images": list(images[:MAX_IMAGES]),
            "duration": int(min(15, max(3, seconds))),
            "aspect_ratio": aspect_ratio,
            "sound": False,
        }

    @staticmethod
    def _classify(msg: str) -> RuntimeError:
        return RefBlocked(msg) if _BLOCK_RE.search(msg or "") else RuntimeError(msg)

    async def generate(self, prompt: str, images: list[str], seconds: int, *,
                       client: httpx.AsyncClient | None = None) -> RefVideoResult:
        key = os.getenv("WAVESPEED_API_KEY")
        if not key:
            raise RuntimeError("WAVESPEED_API_KEY 미설정")
        headers = {"Authorization": f"Bearer {key}"}
        body = self.payload(prompt, images, seconds)
        own = client is None
        client = client or httpx.AsyncClient(timeout=120.0)
        try:
            r = await client.post(f"{BASE_URL}/{self.model_id}", headers=headers, json=body)
            if r.status_code >= 400:
                raise self._classify(f"submit {r.status_code}: {r.text[:500]}")
            task_id = r.json()["data"]["id"]
            waited = 0
            while waited < _MAX_WAIT_SEC:
                await asyncio.sleep(_POLL_SEC)
                waited += _POLL_SEC
                p = await client.get(f"{BASE_URL}/predictions/{task_id}/result", headers=headers)
                if p.status_code >= 400:
                    raise self._classify(f"poll {p.status_code}: {p.text[:500]}")
                data = p.json().get("data") or {}
                status = data.get("status")
                if status == "completed":
                    outputs = data.get("outputs") or []
                    if not outputs:
                        raise RuntimeError("완료됐지만 결과 영상 URL 이 없습니다.")
                    sec = body["duration"]
                    return RefVideoResult(outputs[0], sec, round(sec * self.usd_per_sec, 3),
                                          self.model_id, task_id)
                if status == "failed":
                    raise self._classify(f"failed: {data.get('error') or data}")
            raise RuntimeError(f"영상 생성 대기 시간 초과({_MAX_WAIT_SEC}s)")
        finally:
            if own:
                await client.aclose()


def kling() -> WavespeedRefVideoAdapter:
    return WavespeedRefVideoAdapter(KLING_MODEL, KLING_USD_PER_SEC)


def seedance() -> WavespeedRefVideoAdapter:
    return WavespeedRefVideoAdapter(SEEDANCE_MODEL, SEEDANCE_USD_PER_SEC)
