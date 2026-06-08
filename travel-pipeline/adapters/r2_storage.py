"""완성 영상을 Cloudflare R2에 업로드하고 공개 URL을 반환.

Railway 파일시스템은 휘발성이라 /static 으로 서빙하는 로컬 mp4 는 인스턴스
재시작 시 사라진다. 완성 영상을 R2('videos' 버킷)에 올려 영구 공개 URL을
돌려줘 프론트엔드가 안정적으로 재생/다운로드하게 한다.

boto3 S3 호환 클라이언트 사용: Supabase 413 멀티파트 업로드 한도 문제 해소.
버킷 생성 / Lifecycle 정책은 Cloudflare 대시보드에서 관리한다.

필요 환경변수:
  R2_ACCOUNT_ID        — Cloudflare 계정 ID
  R2_ACCESS_KEY_ID     — R2 API 토큰 (Access Key ID)
  R2_SECRET_ACCESS_KEY — R2 API 토큰 (Secret Access Key)
  R2_BUCKET            — 버킷 이름 (기본값: 'videos')
  R2_PUBLIC_BASE_URL   — 공개 접근 기본 URL (끝 슬래시 포함 여부 무관)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_client = None


def is_available() -> bool:
    """업로드에 필요한 환경변수가 모두 있는지."""
    return bool(
        os.environ.get("R2_ACCOUNT_ID")
        and os.environ.get("R2_ACCESS_KEY_ID")
        and os.environ.get("R2_SECRET_ACCESS_KEY")
        and os.environ.get("R2_PUBLIC_BASE_URL")
    )


def _get_client():
    global _client
    if _client is not None:
        return _client

    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not (account_id and access_key and secret_key):
        raise RuntimeError(
            "R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY 미설정"
        )

    try:
        import boto3
        from botocore.config import Config as BotocoreConfig
    except ImportError as e:
        raise RuntimeError(
            f"boto3 미설치 — pip install boto3>=1.34.0: {e}"
        ) from e

    _client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=BotocoreConfig(signature_version="s3v4"),
    )
    return _client


def upload_video(file_path: str, job_id: str) -> str:
    """영상 파일을 R2에 업로드하고 공개 URL을 반환.

    오브젝트 키: {job_id}/final.mp4
    upload_file 은 boto3 자동 멀티파트 업로드를 사용해 대용량 파일도 처리한다.
    실패 시 예외를 던진다 (호출부에서 로컬 폴백 처리).
    """
    client = _get_client()
    bucket = os.environ.get("R2_BUCKET", "videos")
    object_key = f"{job_id}/final.mp4"

    try:
        client.upload_file(
            file_path,
            bucket,
            object_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
    except Exception as e:
        raise RuntimeError(
            f"R2 업로드 실패(bucket={bucket}, key={object_key}): {e}"
        ) from e

    base_url = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base_url}/{object_key}"


def upload_image(
    file_path: str,
    object_key: str,
    *,
    bucket: str | None = None,
    public_base_url: str | None = None,
    content_type: str = "image/png",
) -> str:
    """임의 이미지 파일을 R2에 업로드하고 공개 URL을 반환.

    bucket / public_base_url 을 주지 않으면 기본 R2_BUCKET / R2_PUBLIC_BASE_URL 을 쓴다.
    실패 시 예외를 던진다(호출부에서 CDN URL 등으로 폴백 처리).
    """
    client = _get_client()
    bucket = bucket or os.environ.get("R2_BUCKET", "videos")
    try:
        client.upload_file(
            file_path, bucket, object_key, ExtraArgs={"ContentType": content_type}
        )
    except Exception as e:
        raise RuntimeError(
            f"R2 이미지 업로드 실패(bucket={bucket}, key={object_key}): {e}"
        ) from e

    base_url = (public_base_url or os.environ.get("R2_PUBLIC_BASE_URL", "")).rstrip("/")
    return f"{base_url}/{object_key}"


def upload_character_sheet(file_path: str, channel_id: str) -> str:
    """캐릭터 시트(채널당 1회, 영구 보존)를 R2에 업로드.

    오브젝트 키: sayeon/characters/{channel_id}/sheet.png

    ⚠️ videos 버킷에는 7일 자동삭제 Lifecycle 이 걸려 있어 시트가 사라질 수 있다.
    Lifecycle 이 없는 전용 버킷(R2_CHARACTER_BUCKET)을 권장하며, 미설정 시 기본
    버킷으로 폴백하되 경고를 남긴다.
    """
    bucket = os.environ.get("R2_CHARACTER_BUCKET")
    public_base = os.environ.get("R2_CHARACTER_PUBLIC_BASE_URL")
    if not bucket:
        logger.warning(
            "R2_CHARACTER_BUCKET 미설정 — 기본 버킷 사용. 7일 Lifecycle 로 시트가 "
            "삭제될 수 있으니 Lifecycle 없는 전용 버킷 설정을 권장합니다."
        )
    object_key = f"sayeon/characters/{channel_id}/sheet.png"
    return upload_image(
        file_path,
        object_key,
        bucket=bucket,
        public_base_url=public_base,
        content_type="image/png",
    )
