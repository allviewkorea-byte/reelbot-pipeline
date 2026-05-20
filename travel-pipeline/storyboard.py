"""
콘티(스토리보드) 이미지 생성 모듈.

영상을 만들기 전에 씬별로 정지 이미지를 먼저 만들어서 사용자가 시각 검증할 수 있게 한다.
- 모델: gpt-image-1, 1024x1536, quality "high"
- 캐릭터 일관성: character_image_path를 reference로 전달 (images.edit API)
- 캐시: 동일 (scene + character + extra) 조합이면 기존 PNG 재사용
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI

from config import Config


_IMAGE_MODEL = "gpt-image-1"
_IMAGE_SIZE = "1024x1536"
_IMAGE_QUALITY = "high"

# 브라우저가 접근할 백엔드 베이스 URL. server.py가 output/ 를 /static 으로 마운트한다.
_PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
_STATIC_MOUNT = "static"


def _to_public_url(image_path: Path, output_root: str) -> str | None:
    """output_root 하위 파일 경로를 브라우저 접근용 절대 URL로 변환.

    예) output/storyboard/{job}/scene_1.png
        -> http://localhost:8000/static/storyboard/{job}/scene_1.png

    image_path가 output_root 밖이면 None.
    """
    try:
        rel = image_path.resolve().relative_to(Path(output_root).resolve())
    except ValueError:
        return None
    return f"{_PUBLIC_BASE_URL}/{_STATIC_MOUNT}/{rel.as_posix()}"


def _scene_cache_key(scene: dict, character_image_path: str, extra: str | None) -> str:
    payload = json.dumps(
        {
            "scene_id": scene.get("scene_id"),
            "description": scene.get("description", ""),
            "camera": scene.get("camera", ""),
            "character": str(character_image_path),
            "extra": extra or "",
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _build_prompt(scene: dict, extra_instructions: str | None = None) -> str:
    description = scene.get("description", "").strip()
    camera = scene.get("camera", "").strip()
    location = scene.get("location", "").strip()

    parts = [
        "Cinematic storyboard frame, single still image (not a video frame sequence).",
        "Maintain the exact same character identity, face, hair, and outfit as in the reference image.",
        "Photorealistic, vertical 9:16 composition, sharp focus, natural lighting.",
    ]
    if camera:
        parts.append(f"Camera: {camera}.")
    if location:
        parts.append(f"Location: {location}.")
    if description:
        parts.append(f"Action / scene: {description}")
    if extra_instructions:
        parts.append(f"Additional direction: {extra_instructions}")
    return " ".join(parts)


def _resolve_character_image(character_image_path: str | None, config: Config) -> str | None:
    """캐릭터 reference 경로 확정.

    프론트에서 character_image_path를 안 보내는 경우(빈 값)가 많아,
    비었으면 config.character_library_front(.env의 CHARACTER_LIBRARY_FRONT) 로 폴백한다.
    최종적으로 실제 존재하는 파일 경로만 반환하고, 없으면 None.
    """
    candidate = (character_image_path or "").strip()
    source = "요청"
    if not candidate:
        candidate = (getattr(config, "character_library_front", "") or "").strip()
        source = "CHARACTER_LIBRARY_FRONT 폴백"

    if candidate and Path(candidate).exists():
        print(f"  [storyboard] 캐릭터 reference 확정({source}): {candidate}")
        return candidate

    if candidate:
        print(f"  [storyboard] ⚠ 캐릭터 reference 파일 없음({source}): {candidate}")
    else:
        print("  [storyboard] ⚠ 캐릭터 reference 미지정 — reference 없이 생성 (캐릭터 일관성 보장 안 됨)")
    return None


def _call_image_api(
    client: OpenAI,
    prompt: str,
    character_image_path: str | None,
) -> bytes:
    """gpt-image-1 호출. character_image_path가 있으면 reference로 edit 사용."""
    char_path = Path(character_image_path) if character_image_path else None

    if char_path and char_path.exists():
        print(f"  [storyboard] gpt-image-1 images.edit 호출 — reference 전달: {char_path}")
        with char_path.open("rb") as f:
            response = client.images.edit(
                model=_IMAGE_MODEL,
                image=f,
                prompt=prompt,
                size=_IMAGE_SIZE,
                quality=_IMAGE_QUALITY,
                n=1,
            )
    else:
        if character_image_path:
            print(f"  [storyboard] ⚠ reference 경로 무효 — reference 없이 images.generate 호출: {character_image_path}")
        else:
            print("  [storyboard] ⚠ reference 없이 images.generate 호출 — 매번 다른 인물이 나올 수 있음")
        response = client.images.generate(
            model=_IMAGE_MODEL,
            prompt=prompt,
            size=_IMAGE_SIZE,
            quality=_IMAGE_QUALITY,
            n=1,
        )

    return base64.b64decode(response.data[0].b64_json)


def _scene_filename(scene_id: int | str) -> str:
    return f"scene_{scene_id}.png"


def _write_meta(image_path: Path, prompt: str, cache_key: str) -> None:
    meta_path = image_path.with_suffix(".json")
    meta_path.write_text(
        json.dumps(
            {"prompt": prompt, "cache_key": cache_key},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_meta(image_path: Path) -> dict | None:
    meta_path = image_path.with_suffix(".json")
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def generate_storyboard(
    scenes: list[dict],
    character_image_path: str,
    output_dir: str,
    config: Config | None = None,
    progress_callback=None,
) -> list[dict]:
    """
    각 씬에 대해 gpt-image-1으로 콘티 이미지 1장씩 생성.

    Args:
        scenes: [{"scene_id": 1, "description": "...", "camera": "wide shot", "location": "..."}, ...]
        character_image_path: 캐릭터 reference 이미지 경로. 비었으면
            config.character_library_front(.env의 CHARACTER_LIBRARY_FRONT)로 폴백.
        output_dir: 출력 폴더 (예: output/storyboard/{job_id}/)
        config: Config 인스턴스 (없으면 새로 생성). OPENAI_API_KEY 필요.
        progress_callback: callable(scene_index, total, message) 형태. 진행률 보고용.

    Returns:
        [{"scene_id": ..., "image_path": "...", "image_url": "...", "prompt": "...", "cached": bool}, ...]
        image_path: 서버 파일시스템 경로(영상 생성 단계에서 reference로 사용)
        image_url: 브라우저 접근용 절대 URL(/static 마운트 경유)
    """
    if config is None:
        config = Config()

    client = OpenAI(api_key=config.openai_api_key)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    character_ref = _resolve_character_image(character_image_path, config)

    results: list[dict] = []
    total = len(scenes)

    for idx, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", idx)
        prompt = _build_prompt(scene)
        cache_key = _scene_cache_key(scene, character_ref or "", None)
        image_path = out_dir / _scene_filename(scene_id)

        cached = False
        existing_meta = _read_meta(image_path)
        if (
            image_path.exists()
            and existing_meta
            and existing_meta.get("cache_key") == cache_key
        ):
            cached = True
            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 캐시 사용")
            print(f"  [storyboard] ({idx}/{total}) 씬 {scene_id} 캐시 재사용")
        else:
            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 콘티 생성 중...")
            print(f"  [storyboard] ({idx}/{total}) 씬 {scene_id} 콘티 생성 중")
            image_bytes = _call_image_api(client, prompt, character_ref)
            image_path.write_bytes(image_bytes)
            _write_meta(image_path, prompt, cache_key)
            print(f"  [storyboard] 저장: {image_path}")

        results.append({
            "scene_id": scene_id,
            "image_path": str(image_path),
            "image_url": _to_public_url(image_path, config.output_dir),
            "prompt": prompt,
            "cached": cached,
        })

    return results


def regenerate_single_scene(
    scene: dict,
    character_image_path: str,
    output_path: str,
    extra_instructions: str | None = None,
    config: Config | None = None,
) -> dict:
    """
    한 씬만 재생성. 사용자가 마음에 안 든 씬을 다시 만들 때 사용.
    캐시 무시하고 무조건 새로 호출.

    Returns: {"scene_id": ..., "image_path": "...", "image_url": "...", "prompt": "...", "cached": False}
    """
    if config is None:
        config = Config()

    client = OpenAI(api_key=config.openai_api_key)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    character_ref = _resolve_character_image(character_image_path, config)
    prompt = _build_prompt(scene, extra_instructions=extra_instructions)
    cache_key = _scene_cache_key(scene, character_ref or "", extra_instructions)

    print(f"  [storyboard] 씬 {scene.get('scene_id')} 재생성 중...")
    image_bytes = _call_image_api(client, prompt, character_ref)
    out_path.write_bytes(image_bytes)
    _write_meta(out_path, prompt, cache_key)
    print(f"  [storyboard] 재생성 저장: {out_path}")

    return {
        "scene_id": scene.get("scene_id"),
        "image_path": str(out_path),
        "image_url": _to_public_url(out_path, config.output_dir),
        "prompt": prompt,
        "cached": False,
    }
