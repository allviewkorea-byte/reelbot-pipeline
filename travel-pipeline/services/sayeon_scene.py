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
    SAYEON_NEGATIVE_SOLO,
    bear_expression,
    build_protagonist_character,
    cast_supporting_animal,
)

logger = logging.getLogger(__name__)

# 시트 reference(주인공 곰)를 항상 쓰는 피사체 유형.
_BEAR_REF_SUBJECTS = ("protagonist", "two_shot", "flashback")


def bear_in_frame(subject_type: str, include_protagonist: bool) -> bool:
    """그 컷에 주인공 곰이 등장하는가 → 시트 reference(Kontext) 경로 사용 여부.

    detail/mood 는 디렉터가 씬 단위로 정한 include_protagonist 로 결정한다
    (곰 일부/작게 담는 게 나은 씬 vs 순수 사물·배경 씬).
    """
    subject = (subject_type or "protagonist").strip().lower()
    if subject in _BEAR_REF_SUBJECTS:
        return True
    if subject in ("detail", "mood"):
        return bool(include_protagonist)
    return True


def build_scene_prompt(
    image_prompt: str,
    anchor: str = "",
    subject_type: str = "protagonist",
    emotion: str = "",
    tone: str = "light",
    other_role: str = "",
    include_protagonist: bool = False,
) -> str:
    """부록 C 템플릿: [STYLE 고정]+[CHARACTER 고정]+[SHOT/SCENE 가변]+[NEGATIVE 고정].

    주인공 곰이 나오는 컷(protagonist/two_shot/flashback, 또는 include_protagonist 인
    detail/mood)에만 캐릭터 블록을 주입한다. two_shot 상대는 캐스팅 팔레트 동물로
    묘사(주인공 외 곰 금지). 표정은 앞부분 강조 + 뒤 반복(Kontext 가 시트 무표정을
    따라가는 문제 완화). 주인공 단독 컷에만 '곰 둘 금지' 네거티브를 추가한다.
    """
    subject = (subject_type or "protagonist").strip().lower()
    bear = bear_in_frame(subject, include_protagonist)
    expr = bear_expression(emotion, tone)
    # [STYLE — 고정]
    parts = [f"{POLAR_BEAR_ART_STYLE}, soft ambient lighting, with subtle texture."]
    # 표정 강조를 앞부분에(반복) — 시트 무표정 추종 완화
    if bear and expr and subject in ("protagonist", "two_shot"):
        parts.append(f"IMPORTANT: the bear's facial expression must clearly read as {expr}.")
    # [CHARACTER — 곰 등장 컷에만]
    if bear:
        character = (anchor or "").strip() or build_protagonist_character(tone)
        if subject in ("detail", "mood"):
            parts.append(
                "The SAME mascot as in the reference sheet appears small or only "
                "partially in frame (e.g., just its paws around the object, or sitting "
                f"small in a corner): {character}."
            )
        elif subject == "flashback":
            parts.append(
                f"The SAME mascot as in the reference sheet, shown in a faded flashback: {character}."
            )
        else:
            parts.append(f"The SAME character as in the reference sheet: {character}.")
        if subject == "two_shot":
            animal = cast_supporting_animal(other_role)
            parts.append(
                f"Other character present: {animal} — a clearly different animal species "
                "(NOT a polar bear), with a distinct base color and silhouette."
            )
        if expr and subject in ("protagonist", "two_shot"):
            parts.append(f"Facial expression: {expr}.")  # 반복 강조
        parts.append(
            "Even in wide, full-body, or over-the-shoulder shots, strictly keep the "
            "same fur, nose, ears, and body proportions as the reference sheet "
            "(same mascot). Vary framing, pose, and background freely, but not the identity."
        )
    else:
        parts.append("No characters in this frame — objects and environment only, no animals.")
    # [SHOT/SCENE — 가변] (디렉터가 구성한 image_prompt: 샷·피사체·동작·장소·무드·감정)
    parts.append((image_prompt or "").strip())
    parts.append(
        "Composition: rule-of-thirds, breathing room, cinematic framing. "
        "9:16 vertical composition. No text, no subtitles, no watermark."
    )
    # [NEGATIVE — 고정] (+ 주인공 단독 컷에만 곰 둘 금지)
    parts.append(f"{SAYEON_NEGATIVE}.")
    if subject == "protagonist":
        parts.append(f"{SAYEON_NEGATIVE_SOLO}.")
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
        other_role = str(scene.get("other_role", "")).strip()
        include_protag = bool(scene.get("include_protagonist", False))
        prompt = build_scene_prompt(
            scene.get("image_prompt", ""),
            anchor,
            subject_type=subject,
            emotion=emotion,
            tone=tone,
            other_role=other_role,
            include_protagonist=include_protag,
        )

        if progress_cb:
            progress_cb(int((idx - 1) / total * 100), f"씬 {index} 생성 중...")

        # 곰 등장 컷은 반드시 시트 reference(Kontext) 경로로 — 주인공 일관성 보장.
        use_reference = bear_in_frame(subject, include_protag)
        logger.info(
            "씬 %s: subject=%s reference=%s%s",
            index, subject, use_reference,
            f" other_role={other_role}" if subject == "two_shot" else "",
        )

        # 첫 후보는 어댑터가 output_path 에 저장한다(scene_{index}_1.png 재사용).
        if not use_reference:
            # 곰 없는 사물/배경 컷: 시트 reference 미적용(t2i). seed 만 전달.
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
