"""어댑터 공용 유틸: 원격 파일 다운로드, 이미지 data URI 변환."""

from __future__ import annotations

import base64
from pathlib import Path


def to_data_uri(path: str) -> str:
    """로컬 이미지 파일을 data URI(base64)로 변환. http(s) URL이면 그대로 반환."""
    if path.startswith(("http://", "https://")):
        return path
    p = Path(path)
    data = base64.b64encode(p.read_bytes()).decode("utf-8")
    suffix = p.suffix.lstrip(".").lower() or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    return f"data:image/{mime};base64,{data}"


async def download_to(client, url: str, dest: str) -> str:
    """url 콘텐츠를 dest 경로에 저장하고 경로 반환."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    resp = await client.get(url)
    resp.raise_for_status()
    dest_path.write_bytes(resp.content)
    return str(dest_path)
