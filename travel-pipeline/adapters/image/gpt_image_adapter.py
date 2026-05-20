"""기존 gpt-image-1 콘티 생성을 어댑터로 wrap.

storyboard.py 의 기존 호출 동작(1024x1536, quality=high, reference 있으면 images.edit)을
그대로 유지한다.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from openai import OpenAI

from ..base import ImageGenerationRequest, ImageGenerationResult, ImageModelAdapter

_IMAGE_MODEL = "gpt-image-1"
_IMAGE_SIZE = "1024x1536"
_IMAGE_QUALITY = "high"


class GptImageAdapter(ImageModelAdapter):
    @property
    def name(self) -> str:
        return "gpt-image-1"

    @property
    def cost_per_image(self) -> float:
        return 0.25  # quality=high 1024x1536 기준

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        char_path = None
        if request.reference_images:
            first = Path(request.reference_images[0])
            if first.exists():
                char_path = first

        if char_path:
            with char_path.open("rb") as f:
                response = client.images.edit(
                    model=_IMAGE_MODEL,
                    image=f,
                    prompt=request.prompt,
                    size=_IMAGE_SIZE,
                    quality=_IMAGE_QUALITY,
                    n=1,
                )
        else:
            response = client.images.generate(
                model=_IMAGE_MODEL,
                prompt=request.prompt,
                size=_IMAGE_SIZE,
                quality=_IMAGE_QUALITY,
                n=1,
            )

        image_bytes = base64.b64decode(response.data[0].b64_json)

        if not request.output_path:
            raise ValueError("GptImageAdapter requires request.output_path")
        out = Path(request.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(image_bytes)

        return ImageGenerationResult(
            image_path=str(out),
            cost_usd=self.cost_per_image,
            model_used=self.name,
            raw_response=response.model_dump() if hasattr(response, "model_dump") else {},
        )
