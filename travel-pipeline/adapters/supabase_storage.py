"""완성 영상을 Supabase Storage에 업로드하고 공개 URL을 반환.

Railway 파일시스템은 휘발성이라 /static 으로 서빙하는 로컬 mp4 는 인스턴스
재시작 시 사라진다. 완성 영상을 Supabase Storage('videos' 버킷)에 올려 영구
공개 URL을 돌려줘 프론트엔드가 안정적으로 재생/다운로드하게 한다.

서버 전용: SUPABASE_SECRET_KEY(service_role) 필요. (Next.js 의 src/lib/supabase.ts
와 동일한 SUPABASE_URL / SUPABASE_SECRET_KEY 규칙을 따른다.)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

VIDEO_BUCKET = "videos"

_client = None


def is_available() -> bool:
    """업로드에 필요한 환경변수가 모두 있는지."""
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


def _get_client():
    global _client
    if _client is not None:
        return _client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SECRET_KEY 미설정")
    from supabase import create_client  # 지연 import (미설치 환경 보호)

    _client = create_client(url, key)
    return _client


def _ensure_bucket(client) -> None:
    """videos 버킷이 없으면 공개(public) 버킷으로 생성. 이미 있으면 그대로 둔다."""
    try:
        buckets = client.storage.list_buckets()
        names = {getattr(b, "name", None) or (b.get("name") if isinstance(b, dict) else None) for b in buckets}
        if VIDEO_BUCKET in names:
            return
    except Exception as e:  # 목록 조회 실패해도 생성 시도
        logger.warning("Supabase 버킷 목록 조회 실패: %s", e)

    # 버전에 따라 create_bucket 시그니처가 다르므로 둘 다 시도.
    try:
        client.storage.create_bucket(VIDEO_BUCKET, options={"public": True})
    except TypeError:
        try:
            client.storage.create_bucket(VIDEO_BUCKET, public=True)
        except Exception as e:
            logger.warning("videos 버킷 생성 실패(이미 존재 가능): %s", e)
    except Exception as e:
        logger.warning("videos 버킷 생성 실패(이미 존재 가능): %s", e)


def upload_video(file_path: str, job_id: str) -> str:
    """영상 파일을 Supabase Storage에 업로드하고 공개 URL을 반환.

    오브젝트 경로: {job_id}/final.mp4 (upsert — 재생성 시 덮어쓴다).
    실패 시 예외를 던진다 (호출부에서 로컬 폴백 처리).
    """
    client = _get_client()
    _ensure_bucket(client)

    object_path = f"{job_id}/final.mp4"
    with open(file_path, "rb") as f:
        data = f.read()

    client.storage.from_(VIDEO_BUCKET).upload(
        object_path,
        data,
        {"content-type": "video/mp4", "upsert": "true"},
    )
    return client.storage.from_(VIDEO_BUCKET).get_public_url(object_path)
