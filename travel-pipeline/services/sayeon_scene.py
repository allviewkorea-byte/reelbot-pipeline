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

from adapters import ImageGenerationRequest, get_image_adapter, get_kontext_adapter, r2_storage
from services.sayeon_character import (
    POLAR_BEAR_ART_STYLE,
    SAYEON_NEGATIVE,
    bear_expression,
    build_protagonist_character,
)

logger = logging.getLogger(__name__)

# 캐릭터 블록(흰곰 바이블)을 주입하는 피사체 유형. detail/mood 는 사물·배경 컷이라
# 미주입(곰이 끼어들지 않도록), flashback 은 약하게(시트 reference 만, 블록 미주입).
_CHARACTER_SUBJECTS = ("protagonist", "two_shot")
# 캐릭터 시트 reference 를 아예 빼는 유형(사물/배경 컷 — Kontext 대신 t2i 사용).
_NO_REFERENCE_SUBJECTS = ("detail", "mood")


def build_scene_prompt(
    image_prompt: str,
    anchor: str = "",
    subject_type: str = "protagonist",
    emotion: str = "",
    tone: str = "light",
) -> str:
    """부록 C 템플릿: [STYLE 고정]+[CHARACTER 고정]+[SHOT/SCENE 가변]+[NEGATIVE 고정].

    CHARACTER 블록은 protagonist/two_shot 에만 주입한다. emotion 은 부록 D 매핑으로
    곰 표정 문구로 변환(serious 톤은 입·몸짓 위주).
    """
    subject = (subject_type or "protagonist").strip().lower()
    # [STYLE — 고정]
    parts = [f"{POLAR_BEAR_ART_STYLE}, soft ambient lighting, with subtle texture."]
    # [CHARACTER — 고정, protagonist/two_shot 에만]
    if subject in _CHARACTER_SUBJECTS:
        character = (anchor or "").strip() or build_protagonist_character(tone)
        parts.append(f"The SAME character as in the reference sheet: {character}.")
        expr = bear_expression(emotion, tone)
        if expr:
            parts.append(f"Facial expression: {expr}.")
        parts.append(
            "Even in wide, full-body, or over-the-shoulder shots, strictly keep the "
            "same fur, nose, ears, and body proportions as the reference sheet "
            "(same mascot). Vary framing, pose, and background freely, but not the identity."
        )
    elif subject in _NO_REFERENCE_SUBJECTS:
        parts.append("No characters in this frame — objects and environment only.")
    # [SHOT/SCENE — 가변] (디렉터가 구성한 image_prompt: 샷·피사체·동작·장소·무드·감정)
    parts.append((image_prompt or "").strip())
    parts.append(
        "Composition: rule-of-thirds, breathing room, cinematic framing. "
        "9:16 vertical composition. No text, no subtitles, no watermark."
    )
    # [NEGATIVE — 고정]
    parts.append(f"{SAYEON_NEGATIVE}.")
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
    tone: str = "light",
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

    # 사물/배경(detail/mood) 컷용 t2i 어댑터 — 시트 reference 없이 생성해 곰 미등장 보장.
    t2i_adapter = get_image_adapter()

    for idx, scene in enumerate(scenes, 1):
        index = scene.get("index", idx)
        subject = str(scene.get("subject_type", "protagonist")).strip().lower()
        emotion = str(scene.get("emotion", "")).strip()
        prompt = build_scene_prompt(
            scene.get("image_prompt", ""),
            anchor,
            subject_type=subject,
            emotion=emotion,
            tone=tone,
        )

        if progress_cb:
            progress_cb(int((idx - 1) / total * 100), f"씬 {index} 생성 중...")

        # 첫 후보는 어댑터가 output_path 에 저장한다(scene_{index}_1.png 재사용).
        if subject in _NO_REFERENCE_SUBJECTS:
            # detail/mood: 캐릭터 시트 reference 미적용(t2i). seed 만 전달.
            extra_t2i: dict = {}
            if seed is not None and seed >= 0:
                extra_t2i["seed"] = seed
            request = ImageGenerationRequest(
                prompt=prompt,
                aspect_ratio="9:16",
                output_path=str(out_dir / f"scene_{index}_1.png"),
                extra_params=extra_t2i or None,
            )
            result = asyncio.run(t2i_adapter.generate(request))
        else:
            extra: dict = {"num_images": num_images}
            if seed is not None and seed >= 0:
                extra["seed"] = seed
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
