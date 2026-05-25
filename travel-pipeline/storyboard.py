"""
콘티(스토리보드) 이미지 생성 모듈.

영상을 만들기 전에 씬별로 정지 이미지를 먼저 만들어서 사용자가 시각 검증할 수 있게 한다.
- 모델: WaveSpeed 스케치(z-image/turbo), 9:16 — 흑백 연필 스케치 톤
- 스타일: storyboard sketch / pencil drawing / black and white 를 프롬프트로 강제
- 캐시: 동일 (scene + character + extra) 조합이면 기존 PNG 재사용
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

from adapters import ImageGenerationRequest, get_image_adapter
from config import Config

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


def _preview_url(source_url: str | None, image_path: Path, output_root: str) -> str | None:
    """브라우저 미리보기용 URL. 외부 접근 가능한 CDN URL(source_url)을 우선 쓰고,
    없을 때만 /static 마운트 경유 로컬 URL로 폴백한다.

    배포(Railway)에서는 PUBLIC_BASE_URL 미설정·로컬 파일 휘발성 때문에 /static
    경로가 깨지므로, WaveSpeed CDN URL을 직접 전달하는 것이 안정적이다.
    """
    if source_url:
        return source_url
    return _to_public_url(image_path, output_root)


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

    # 콘티는 흑백 연필 스케치 톤으로 강제한다. (z-image/turbo 는 negative prompt 를
    # 보장하지 않으므로 'black and white / pencil' 을 positive 프롬프트로 명시해 컬러·사진풍을 배제)
    parts = [
        "Storyboard sketch, pencil drawing, black and white, cinematic frame.",
        "Single still image, vertical 9:16 composition, clean linework, no color.",
    ]
    if camera:
        parts.append(f"Camera: {camera}.")
    if location:
        parts.append(f"Location: {location}.")
    if description:
        parts.append(f"Scene: {description}")
    if extra_instructions:
        parts.append(f"Additional direction: {extra_instructions}")
    return " ".join(parts)


def _generate_image(
    adapter,
    prompt: str,
    character_image_path: str | None,
    output_path: Path,
):
    """선택된 어댑터로 콘티 이미지 1장 생성 후 output_path에 저장. 결과 객체 반환."""
    references = None
    if character_image_path:
        references = [character_image_path]
    request = ImageGenerationRequest(
        prompt=prompt,
        reference_images=references,
        aspect_ratio="9:16",
        output_path=str(output_path),
    )
    return asyncio.run(adapter.generate(request))


def _scene_filename(scene_id: int | str) -> str:
    return f"scene_{scene_id}.png"


def _write_meta(
    image_path: Path, prompt: str, cache_key: str, source_url: str | None = None
) -> None:
    meta_path = image_path.with_suffix(".json")
    meta_path.write_text(
        json.dumps(
            {"prompt": prompt, "cache_key": cache_key, "source_url": source_url},
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
    model: str = "default",
) -> list[dict]:
    """
    각 씬에 대해 WaveSpeed 스케치 모델로 콘티 이미지 1장씩 생성.

    Args:
        scenes: [{"scene_id": 1, "description": "...", "camera": "wide shot", "location": "..."}, ...]
        character_image_path: 캐릭터 reference 이미지 경로 (없으면 reference 없이 생성)
        output_dir: 출력 폴더 (예: output/storyboard/{job_id}/)
        config: Config 인스턴스 (없으면 새로 생성). WAVESPEED_API_KEY 필요(없으면 gpt-image fallback).
        progress_callback: callable(scene_index, total, message) 형태. 진행률 보고용.

    Returns:
        [{"scene_id": ..., "image_path": "...", "image_url": "...", "prompt": "...", "cached": bool}, ...]
        image_path: 서버 파일시스템 경로(영상 생성 단계에서 reference로 사용)
        image_url: 브라우저 접근용 URL. WaveSpeed CDN URL 우선, 없으면 /static 마운트 경유.
    """
    if config is None:
        config = Config()

    adapter = get_image_adapter(model)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    total = len(scenes)

    for idx, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", idx)
        prompt = _build_prompt(scene)
        cache_key = _scene_cache_key(scene, character_image_path, None)
        image_path = out_dir / _scene_filename(scene_id)

        cached = False
        source_url: str | None = None
        existing_meta = _read_meta(image_path)
        if (
            image_path.exists()
            and existing_meta
            and existing_meta.get("cache_key") == cache_key
        ):
            cached = True
            source_url = existing_meta.get("source_url")
            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 캐시 사용")
            print(f"  [storyboard] ({idx}/{total}) 씬 {scene_id} 캐시 재사용")
        else:
            if progress_callback:
                progress_callback(idx, total, f"씬 {scene_id} 콘티 생성 중...")
            print(f"  [storyboard] ({idx}/{total}) 씬 {scene_id} 콘티 생성 중 (모델: {adapter.name})")
            result = _generate_image(adapter, prompt, character_image_path, image_path)
            source_url = getattr(result, "source_url", None)
            _write_meta(image_path, prompt, cache_key, source_url)
            print(f"  [storyboard] 저장: {image_path}")

        results.append({
            "scene_id": scene_id,
            "image_path": str(image_path),
            "image_url": _preview_url(source_url, image_path, config.output_dir),
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
    model: str = "default",
) -> dict:
    """
    한 씬만 재생성. 사용자가 마음에 안 든 씬을 다시 만들 때 사용.
    캐시 무시하고 무조건 새로 호출.

    Returns: {"scene_id": ..., "image_path": "...", "image_url": "...", "prompt": "...", "cached": False}
    """
    if config is None:
        config = Config()

    adapter = get_image_adapter(model)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = _build_prompt(scene, extra_instructions=extra_instructions)
    cache_key = _scene_cache_key(scene, character_image_path, extra_instructions)

    print(f"  [storyboard] 씬 {scene.get('scene_id')} 재생성 중 (모델: {adapter.name})")
    result = _generate_image(adapter, prompt, character_image_path, out_path)
    source_url = getattr(result, "source_url", None)
    _write_meta(out_path, prompt, cache_key, source_url)
    print(f"  [storyboard] 재생성 저장: {out_path}")

    return {
        "scene_id": scene.get("scene_id"),
        "image_path": str(out_path),
        "image_url": _preview_url(source_url, out_path, config.output_dir),
        "prompt": prompt,
        "cached": False,
    }
