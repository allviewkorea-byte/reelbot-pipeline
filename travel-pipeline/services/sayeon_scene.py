"""사연 트랙 — 씬 이미지 생성 (PR-S2b).

저장된 캐릭터 시트(PR-S2a)를 reference 로 FLUX Kontext Pro Multi 에 넣어
동일 인물·웹툰 스타일의 씬 이미지를 생성한다. 씬당 num_images 장 생성해
큐레이션(베스트 선택)할 수 있게 후보를 모두 반환한다.

씬 프롬프트(image_prompt)는 PR-S1(씬 분할)이 공급한다. 여기서는 그 프롬프트에
스타일·정체성 앵커·9:16·'no text' 제약을 덧씌운다(이미지에 자막은 절대 넣지 않음 —
자막은 합성 단계 PR-S4 에서 번인).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from adapters import ImageGenerationRequest, get_kontext_adapter, r2_storage
from services.sayeon_character import SAYEON_IMAGE_STYLE

logger = logging.getLogger(__name__)


def build_scene_prompt(image_prompt: str, anchor: str = "") -> str:
    """씬 묘사 + 스타일/정체성 앵커/9:16/no-text 제약을 합친 최종 프롬프트."""
    parts = [
        "Korean webtoon (manhwa) style, flat color with soft cel shading.",
        "The SAME character as in the reference image.",
        (image_prompt or "").strip(),
    ]
    if anchor and anchor.strip():
        parts.append(
            f"Keep the exact same identity: {anchor.strip()}. "
            "Same face, hair, outfit, and accessories."
        )
    # 와이드·풀·OTS 샷에서도 시트 참조로 동일 인물 유지(연출 다양성과 일관성의 균형).
    parts.append(
        "Even in wide, full-body, or over-the-shoulder shots, strictly keep the same "
        "face, hairstyle, outfit, and accessories as the reference character sheet "
        "(same person). Vary framing, pose, and background freely, but not the identity."
    )
    parts.append("9:16 vertical composition. No text, no subtitles, no watermark.")
    parts.append(f"{SAYEON_IMAGE_STYLE}.")
    return " ".join(p for p in parts if p)


def _download_sync(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)


def generate_scenes(
    job_id: str,
    sheet_url: str,
    scenes: list[dict],
    anchor: str = "",
    num_images: int = 2,
    seed: int = -1,
    output_dir: str | None = None,
    progress_cb=None,
) -> dict:
    """각 씬을 Kontext 로 num_images 장씩 생성하고 후보들을 R2에 올린다.

    Args:
        sheet_url: PR-S2a 가 만든 캐릭터 시트 공개 URL (reference)
        scenes: [{"index": 1, "image_prompt": "..."}, ...] (PR-S1 산출물; 추가 필드 무시)
        anchor: 정체성 앵커 문구(모든 프롬프트에 반복해 드리프트 억제)
        num_images: 씬당 후보 장수(큐레이션)

    Returns:
        {"scenes": [{"index", "image_urls"[후보], "selected_url", "prompt",
                      "candidate_count"}], "total_cost_usd"}
    """
    if not sheet_url:
        raise ValueError("sheet_url 필요 — 먼저 캐릭터 시트(PR-S2a)를 생성하세요.")

    adapter = get_kontext_adapter()
    if not adapter.is_available():
        raise RuntimeError("WAVESPEED_API_KEY 미설정 — 씬을 생성할 수 없습니다.")

    out_dir = Path(output_dir or f"output/sayeon/scenes/{job_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total = max(len(scenes), 1)
    total_cost = 0.0

    for idx, scene in enumerate(scenes, 1):
        index = scene.get("index", idx)
        prompt = build_scene_prompt(scene.get("image_prompt", ""), anchor)

        if progress_cb:
            progress_cb(int((idx - 1) / total * 100), f"씬 {index} 생성 중...")

        extra: dict = {"num_images": num_images}
        if seed is not None and seed >= 0:
            extra["seed"] = seed
        # 첫 후보는 어댑터가 output_path 에 저장한다(scene_{index}_1.png 재사용).
        request = ImageGenerationRequest(
            prompt=prompt,
            reference_images=[sheet_url],
            aspect_ratio="9:16",
            output_path=str(out_dir / f"scene_{index}_1.png"),
            extra_params=extra,
        )
        result = asyncio.run(adapter.generate(request))
        total_cost += result.cost_usd

        candidates = []
        if isinstance(result.raw_response, dict):
            candidates = result.raw_response.get("outputs") or []

        image_urls: list[str] = []
        for k, cdn_url in enumerate(candidates, 1):
            local = out_dir / f"scene_{index}_{k}.png"
            public = cdn_url  # R2 미설정/실패 시 CDN URL 폴백
            if r2_storage.is_available():
                try:
                    if not local.exists():
                        _download_sync(cdn_url, local)
                    public = r2_storage.upload_image(
                        str(local), f"sayeon/scenes/{job_id}/scene_{index}_{k}.png"
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("씬 이미지 R2 업로드 실패, CDN URL 사용: %s", e)
                    public = cdn_url
            image_urls.append(public)

        results.append({
            "index": index,
            "image_urls": image_urls,
            "selected_url": image_urls[0] if image_urls else None,
            "prompt": prompt,
            "candidate_count": len(image_urls),
        })

    if progress_cb:
        progress_cb(100, "완료")
    return {"scenes": results, "total_cost_usd": round(total_cost, 4)}
