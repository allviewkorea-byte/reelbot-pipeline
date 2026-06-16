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
import os
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
    ensure_brownbear_sheet,
)

logger = logging.getLogger(__name__)

# 시트 reference(주인공 곰)를 항상 쓰는 피사체 유형.
_BEAR_REF_SUBJECTS = ("protagonist", "two_shot", "flashback")

# 보조 시트 파일럿(SAYEON_SUPPORTING_SHEETS): 갈색곰으로 캐스팅되는 two_shot 역할.
_BROWN_BEAR_ROLES = {"friend", "advisor", "family"}
# 멀티 레퍼런스 시 두 캐릭터 매칭·섞임 방지 지시(레퍼런스1=흰곰 / 레퍼런스2=갈색곰).
_MULTI_REF_NOTE = (
    " Reference image 1 is the white polar bear (the protagonist); reference image 2 is the "
    "brown bear (the other character). Match each animal to its own reference and keep them as "
    "two clearly distinct animals — do NOT blend, merge, or swap their fur colors or features."
)


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
    context: str = "",
) -> str:
    """부록 C 템플릿: [STYLE 고정]+[CHARACTER 고정]+[SHOT/SCENE 가변]+[NEGATIVE 고정].

    주인공 곰이 나오는 컷(protagonist/two_shot/flashback, 또는 include_protagonist 인
    detail/mood)에만 캐릭터 블록을 주입한다. two_shot 상대는 캐스팅 팔레트 동물로
    묘사(주인공 외 곰 금지). 표정은 **프롬프트 맨 앞에 대문자로 최우선 강조 + 끝에서
    1회 더 반복**(총 2회)해 Kontext 가 시트 무표정을 따라가는 문제를 강하게 억제한다.
    protagonist 컷에 표정이 비면 deadpan 을 강제한다. 주인공 단독 컷엔 '곰 둘 금지'
    네거티브를 추가한다.
    """
    subject = (subject_type or "protagonist").strip().lower()
    bear = bear_in_frame(subject, include_protagonist)
    emo = (emotion or "").strip().lower()
    # protagonist 컷은 표정 미명시 시 deadpan 강제(시트 무표정 추종 방지).
    if subject == "protagonist" and not emo:
        emo = "deadpan"
    expr = bear_expression(emo, tone)
    show_expr = bool(bear and expr and subject in ("protagonist", "two_shot"))
    parts: list[str] = []
    # [표정 — 최우선/앞] 곰 표정 컷은 프롬프트 맨 앞에 대문자로 최우선 강조(1회째).
    if show_expr:
        parts.append(f"FACIAL EXPRESSION: {expr} — THIS IS THE MOST IMPORTANT.")
    # [STYLE — 고정]
    parts.append(f"{POLAR_BEAR_ART_STYLE}, soft ambient lighting, with subtle texture.")
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
            animal = cast_supporting_animal(other_role, context)
            parts.append(
                f"Other character present: {animal} — a clearly different animal species "
                "(NOT a polar bear), with a distinct base color and silhouette."
            )
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
    # [표정 — 끝/반복] 2회째: 표정을 끝에서 한 번 더 못박는다(시트 무표정 추종 완화).
    if show_expr:
        parts.append(
            f"Again — the polar bear's facial expression MUST clearly read as {expr}; "
            "prioritize this expression over copying the neutral face of the reference sheet."
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

    # 보조 시트 파일럿(기본 off=현재 동작). on 일 때만 갈색곰 two_shot 에 2번째 레퍼런스 추가.
    supporting_sheets_on = (os.getenv("SAYEON_SUPPORTING_SHEETS") or "").strip().lower() in (
        "1", "true", "on", "yes",
    )
    # 채널 단위 안정 키로 갈색곰 시트 재사용(영상마다 재생성 금지). 처음 필요할 때 1회 확보.
    supporting_channel = (os.getenv("SAYEON_CHANNEL_ID") or "baekgom").strip() or "baekgom"
    brown_sheet_url: str | None = None
    brown_tried = False

    for idx, scene in enumerate(scenes, 1):
        index = scene.get("index", idx)
        subject = str(scene.get("subject_type", "protagonist")).strip().lower()
        emotion = str(scene.get("emotion", "")).strip()
        other_role = str(scene.get("other_role", "")).strip()
        include_protag = bool(scene.get("include_protagonist", False))
        # 갈색곰(family) 게이팅용 한국어 씬 텍스트(가족 키워드 판별).
        context = f"{scene.get('narration', '')} {scene.get('subtitle', '')}"
        prompt = build_scene_prompt(
            scene.get("image_prompt", ""),
            anchor,
            subject_type=subject,
            emotion=emotion,
            tone=tone,
            other_role=other_role,
            include_protagonist=include_protag,
            context=context,
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
            refs = [sheet_url]
            scene_prompt = prompt
            # 파일럿: 갈색곰(friend/advisor/family) two_shot 에 갈색곰 시트를 2번째 레퍼런스로.
            if (
                supporting_sheets_on
                and subject == "two_shot"
                and other_role.lower() in _BROWN_BEAR_ROLES
            ):
                if not brown_tried:
                    brown_tried = True
                    brown_sheet_url = ensure_brownbear_sheet(supporting_channel)
                if brown_sheet_url:
                    refs = [sheet_url, brown_sheet_url]
                    scene_prompt = prompt + _MULTI_REF_NOTE  # 매칭·섞임 방지 지시 추가
                    logger.info("씬 %s: 멀티 레퍼런스(흰곰+갈색곰) 적용", index)
            request = ImageGenerationRequest(
                prompt=scene_prompt,
                reference_images=refs,
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
