"""완성 영상을 Supabase Storage에 업로드하고 공개 URL을 반환.

Railway 파일시스템은 휘발성이라 /static 으로 서빙하는 로컬 mp4 는 인스턴스
재시작 시 사라진다. 완성 영상을 Supabase Storage('videos' 버킷)에 올려 영구
공개 URL을 돌려줘 프론트엔드가 안정적으로 재생/다운로드하게 한다.

서버 전용: SUPABASE_SECRET_KEY(service_role) 필요. (Next.js 의 src/lib/supabase.ts
와 동일한 SUPABASE_URL / SUPABASE_SECRET_KEY 규칙을 따른다.)
"""

from __future__ import annotations

import os

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
    """videos 버킷이 없으면 공개(public) 버킷으로 생성. 이미 있으면 그대로 둔다.

    실패는 조용히 삼키지 않고 stdout(Railway 로그)에 분명히 남긴다.
    """
    try:
        buckets = client.storage.list_buckets()
        names = {getattr(b, "name", None) or (b.get("name") if isinstance(b, dict) else None) for b in buckets}
        if VIDEO_BUCKET in names:
            return
    except Exception as e:
        # 목록 조회 실패는 anon 키/권한 문제일 수 있으므로 분명히 알린다.
        print(f"  [supabase] 버킷 목록 조회 실패(service_role 키/권한 확인 필요): {e}")

    # 버전에 따라 create_bucket 시그니처가 다르므로 둘 다 시도.
    try:
        try:
            client.storage.create_bucket(VIDEO_BUCKET, options={"public": True})
        except TypeError:
            client.storage.create_bucket(VIDEO_BUCKET, public=True)
        print(f"  [supabase] '{VIDEO_BUCKET}' 버킷 생성(public)")
    except Exception as e:
        # 이미 존재하면 정상. 그 외(권한 등)는 이어지는 upload 에서 다시 드러난다.
        print(f"  [supabase] '{VIDEO_BUCKET}' 버킷 생성 생략(이미 존재하거나 권한 부족): {e}")


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

    try:
        client.storage.from_(VIDEO_BUCKET).upload(
            object_path,
            data,
            {"content-type": "video/mp4", "upsert": "true"},
        )
    except Exception as e:
        # 사유를 분명히 표면화. 권한/RLS 오류면 service_role 키 여부를 의심해야 한다.
        raise RuntimeError(
            f"Supabase Storage 업로드 실패(bucket={VIDEO_BUCKET}, path={object_path}): {e}. "
            "SUPABASE_SECRET_KEY 가 anon 이 아닌 service_role 키인지, 'videos' 버킷/정책을 확인하세요."
        ) from e

    return client.storage.from_(VIDEO_BUCKET).get_public_url(object_path)
