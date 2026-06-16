"""사연 동물 캐스트 — 캐릭터 시트 관리 화면(프론트 /cast)용 백엔드 서비스.

8캐스트(바이블)를 역할(role) 단위로 정의하고, 역할별 고정 파일명으로 시트를 1장
생성해 R2에 저장한다. 흰곰 주인공/보조(갈색곰) 시트는 기존 파이프라인이 쓰는
키(sheet.png / brownbear.png)를 그대로 재사용해 충돌·중복 생성을 막는다.

⚠️ 실제 씬 멀티레퍼런스(sayeon_scene) 연결·CASTING_PALETTE 정합은 이번 범위가 아니다.
여기서는 "역할 → 동물 → R2 파일명" 컨벤션과 시트 생성/조회만 담당한다.

생성 엔진은 신규 벤더 없이 기존 WaveSpeed 이미지 어댑터를 재사용한다(스타일은
프롬프트로 강제). 시트는 채널당 1회만 만들면 되므로 Railway 휘발성 파일시스템에
남기지 않고 R2 영구 URL 을 돌려준다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from adapters import ImageGenerationRequest, r2_storage
from adapters.image.wavespeed_image_adapter import WavespeedImageAdapter
from services.sayeon_character import (
    DEFAULT_SHEET_MODEL,
    _BROWN_BEAR_CORE,
    build_protagonist_character,
    build_supporting_sheet_prompt,
)

logger = logging.getLogger(__name__)

# ── 캐스트 바이블 (역할 → 동물 / 성격 / 시트 프롬프트 코어 / R2 파일명) ──────
# 주인공(흰곰)·가족(갈색곰)은 기존 파이프라인이 쓰는 파일명을 그대로 재사용한다
# (sheet.png / brownbear.png). 나머지는 역할별 고정 신규 파일명으로 충돌을 막는다.
# core 는 build_supporting_sheet_prompt 가 감싸는 캐릭터 묘사(눈 표현 포함).
CAST_BIBLE: list[dict] = [
    {
        "role": "protagonist",
        "name": "흰곰 · 주인공",
        "animal": "흰곰",
        "personality": "평범하고 공감되는 '나'. 사연을 이끄는 1인칭 화자.",
        "filename": "sheet.png",
        "core": build_protagonist_character("light"),
    },
    {
        "role": "narrator",
        "name": "흰곰 · 전지모드",
        "animal": "흰곰(선글라스)",
        "personality": "쿨한 해설자. 내레이션과 반전 폭로를 담당.",
        "filename": "narrator.png",
        "core": build_protagonist_character("serious"),
    },
    {
        "role": "male_lead",
        "name": "시바견 · 그",
        "animal": "시바견",
        "personality": "남성 상대역 또는 남성 가해자.",
        "filename": "male_lead.png",
        "core": (
            "a chubby round shiba-dog mascot with short stubby limbs "
            "(NOT realistic-dog proportions), warm tan-and-cream fur, small pointed "
            "perky ears, a small black nose, and round dark expressive eyes"
        ),
    },
    {
        "role": "female_lead",
        "name": "토끼 · 그녀",
        "animal": "토끼",
        "personality": "여성 상대역 또는 여성 가해자.",
        "filename": "female_lead.png",
        "core": (
            "a chubby round rabbit mascot with short stubby limbs, soft cream-colored "
            "fur, long upright ears, a tiny pink nose, and large round expressive eyes"
        ),
    },
    {
        "role": "friend_squirrel",
        "name": "다람쥐 · 친구",
        "animal": "다람쥐",
        "personality": "활발한 정보통. 사이다 같은 친구.",
        "filename": "friend_squirrel.png",
        "core": (
            "a chubby round squirrel mascot with short stubby limbs, warm "
            "reddish-brown fur, a big fluffy tail, small tufted ears, and bright "
            "lively round eyes"
        ),
    },
    {
        "role": "friend_penguin",
        "name": "펭귄 · 친구",
        "animal": "펭귄",
        "personality": "차분하고 의리 있는 친구. 끝에 진심을 보인다.",
        "filename": "friend_penguin.png",
        "core": (
            "a chubby round baby penguin mascot with short stubby flippers, "
            "black-and-white plumage, a small round orange beak, and calm round "
            "dark eyes"
        ),
    },
    {
        "role": "family_bear",
        "name": "갈색곰 · 가족",
        "animal": "갈색곰",
        "personality": "부모·시댁 등 가족. 따뜻하지만 갈등의 진원.",
        "filename": "brownbear.png",
        "core": _BROWN_BEAR_CORE,
    },
    {
        "role": "villain",
        "name": "너구리 · 악역",
        "animal": "너구리",
        "personality": "교활한 외부 빌런. 진상·갑질·사기.",
        "filename": "villain.png",
        "core": (
            "a chubby round raccoon mascot with short stubby limbs, gray fur with a "
            "dark mask marking around the eyes, a ringed bushy tail, small rounded "
            "ears, and narrow sly eyes"
        ),
    },
]

# role → bible 엔트리(빠른 조회).
_CAST_BY_ROLE = {entry["role"]: entry for entry in CAST_BIBLE}


def get_cast_entry(role: str) -> dict | None:
    """역할 키로 캐스트 바이블 엔트리를 찾는다(없으면 None)."""
    return _CAST_BY_ROLE.get((role or "").strip().lower())


def _public_entry(entry: dict, channel_id: str) -> dict:
    """프론트로 내려줄 캐스트 1건(프롬프트 코어는 제외, R2 시트 URL 포함)."""
    sheet_url: str | None = None
    if r2_storage.is_available() and r2_storage.character_sheet_exists(
        channel_id, entry["filename"]
    ):
        sheet_url = r2_storage.character_sheet_url(channel_id, entry["filename"])
    return {
        "role": entry["role"],
        "name": entry["name"],
        "animal": entry["animal"],
        "personality": entry["personality"],
        "filename": entry["filename"],
        "sheet_url": sheet_url,
    }


def list_cast(channel_id: str) -> list[dict]:
    """8캐스트 메타 + R2 시트 URL(있으면) 목록. status 는 프론트(Supabase)가 병합."""
    return [_public_entry(entry, channel_id) for entry in CAST_BIBLE]


def generate_cast_sheet(
    channel_id: str,
    role: str,
    output_dir: str | None = None,
) -> dict:
    """역할별 캐스트 시트 1장을 생성하고 R2(역할별 고정 파일명)에 저장한다.

    Returns:
        {"role", "name", "animal", "filename", "sheet_url", "persistent"}
    실패(미설정·생성 오류)는 예외로 던진다(호출부에서 처리).
    """
    entry = get_cast_entry(role)
    if not entry:
        raise ValueError(f"알 수 없는 캐스트 역할입니다: {role}")

    adapter = WavespeedImageAdapter(model_id=DEFAULT_SHEET_MODEL)
    if not adapter.is_available():
        raise RuntimeError("WAVESPEED_API_KEY 미설정 — 캐스트 시트를 생성할 수 없습니다.")

    out_dir = Path(output_dir or f"output/sayeon/characters/{channel_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / entry["filename"]

    prompt = build_supporting_sheet_prompt(entry["core"])
    result = asyncio.run(
        adapter.generate(
            ImageGenerationRequest(
                prompt=prompt, aspect_ratio="9:16", output_path=str(local_path)
            )
        )
    )

    sheet_url: str | None = None
    persistent = False
    if r2_storage.is_available():
        try:
            sheet_url = r2_storage.upload_character_sheet(
                str(local_path), channel_id, filename=entry["filename"]
            )
            persistent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("캐스트 시트 R2 업로드 실패, CDN URL 폴백: %s", e)
    if not sheet_url:
        # R2 미설정/실패 → WaveSpeed CDN URL 폴백(임시). 운영에선 R2 필수.
        sheet_url = result.source_url
        logger.warning(
            "캐스트 시트가 R2에 영구 저장되지 않았습니다(임시 CDN URL). R2_* 환경변수를 설정하세요."
        )

    return {
        "role": entry["role"],
        "name": entry["name"],
        "animal": entry["animal"],
        "filename": entry["filename"],
        "sheet_url": sheet_url,
        "persistent": persistent,
    }
