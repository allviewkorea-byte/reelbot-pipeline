"""1회성 스크립트 — Meta Muse Image(WaveSpeed) 첫 실호출로 파라미터 확인 (A0-3).

얼굴 1장(text-to-image, 3:4) → 그 결과 URL 을 참조로 헤어 1장(edit, image_urls) = 총 2장, 약 $0.022.
DB·R2 는 건드리지 않는다. 제출 페이로드와 WaveSpeed 응답 요약을 그대로 출력한다.
사용법(WAVESPEED_API_KEY 필요):
  cd travel-pipeline
  py scripts/probe_muse.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from adapters.base import ImageGenerationRequest  # noqa: E402
from adapters.image.muse_adapter import MuseImageAdapter  # noqa: E402
from services import character_studio_gen as gen  # noqa: E402

BIBLE = {"subject_en": "woman", "age": 24, "height_cm": 172,
         "summary_en": "24-year-old Korean woman, an office worker living in Seoul",
         "hair_en": "long straight black hair"}


async def main() -> None:
    adapter = MuseImageAdapter()
    if not adapter.is_available():
        sys.exit("WAVESPEED_API_KEY 미설정")
    tmp = Path(tempfile.mkdtemp(prefix="probe_muse_"))
    face_req = ImageGenerationRequest(prompt=gen.face_prompt(BIBLE), aspect_ratio="3:4", output_path=str(tmp / "face.png"))
    print("① face payload:", json.dumps(adapter.build(face_req), ensure_ascii=False, indent=1))
    face = await adapter.generate(face_req)
    print("① face →", face.model_used, face.source_url, f"${face.cost_usd}",
          json.dumps({k: face.raw_response.get(k) for k in ("status", "outputs", "timings", "has_nsfw_contents")}))
    hair_req = ImageGenerationRequest(prompt=gen.hair_prompt(BIBLE, gen.HAIR_PRESETS[4]["line"]),
                                      reference_images=[face.source_url], aspect_ratio="3:4",
                                      output_path=str(tmp / "hair.png"))
    print("② hair payload:", json.dumps(adapter.build(hair_req), ensure_ascii=False, indent=1))
    hair = await adapter.generate(hair_req)
    print("② hair →", hair.model_used, hair.source_url, f"${hair.cost_usd}",
          json.dumps({k: hair.raw_response.get(k) for k in ("status", "outputs", "timings", "has_nsfw_contents")}))
    print("저장 위치:", tmp)


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
