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


def upload_audio(file_path: str, job_id: str, filename: str = "narration.wav") -> str:
    """나레이션 오디오를 R2(기본 videos 버킷)에 업로드하고 공개 URL 반환.

    오브젝트 키: sayeon/audio/{job_id}/{filename}
    영구 보존이 아니라 S4 합성이 소비하는 중간 산출물이므로 기본 버킷으로 충분하다.
    """
    object_key = f"sayeon/audio/{job_id}/{filename}"
    content_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    return upload_image(file_path, object_key, content_type=content_type)


def upload_sayeon_video(file_path: str, job_id: str) -> str:
    """사연 완성 영상을 R2(기본 videos 버킷)에 업로드하고 공개 URL 반환.

    오브젝트 키: sayeon/videos/{job_id}/final.mp4
    """
    object_key = f"sayeon/videos/{job_id}/final.mp4"
    return upload_image(file_path, object_key, content_type="video/mp4")


def _bgm_bucket() -> str:
    """BGM 전용 버킷. 미설정 시 기본 버킷으로 폴백한다.

    ⚠️ 기본(videos) 버킷에는 7일 자동삭제 Lifecycle 이 걸려 있어 BGM 자산이
    사라질 수 있다. Lifecycle 없는 전용 버킷(R2_BGM_BUCKET) 사용을 권장한다.
    """
    bucket = os.environ.get("R2_BGM_BUCKET")
    if not bucket:
        logger.warning(
            "R2_BGM_BUCKET 미설정 — 기본 버킷 사용. 7일 Lifecycle 로 BGM 이 삭제될 "
            "수 있으니 Lifecycle 없는 전용 버킷 설정을 권장합니다."
        )
    return bucket or os.environ.get("R2_BUCKET", "videos")


# BGM 으로 인정하는 오디오 확장자.
_BGM_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")


def list_bgm_keys(mood: str) -> list[str]:
    """bgm/{mood}/ 아래 오디오 오브젝트 키 목록(폴더 자체·비오디오 제외).

    mood: emotional | suspense | hopeful. 호출부가 이 중 무작위로 한 곡을 고른다.
    """
    client = _get_client()
    bucket = _bgm_bucket()
    prefix = f"bgm/{mood.strip('/')}/"
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if key.lower().endswith(_BGM_EXTS):
                keys.append(key)
    return keys


def download_bgm(object_key: str, dest: str) -> str:
    """BGM 오브젝트를 로컬 dest 로 내려받는다(서버사이드 합성용, 공개 URL 불필요)."""
    client = _get_client()
    bucket = _bgm_bucket()
    try:
        client.download_file(bucket, object_key, dest)
    except Exception as e:
        raise RuntimeError(
            f"R2 BGM 다운로드 실패(bucket={bucket}, key={object_key}): {e}"
        ) from e
    return dest


def upload_character_sheet(file_path: str, channel_id: str, filename: str = "sheet.png") -> str:
    """캐릭터 시트(채널당 1회, 영구 보존)를 R2에 업로드.

    오브젝트 키: sayeon/characters/{channel_id}/{filename}
    filename 기본 sheet.png(주인공). 보조 캐릭터는 신규 키(예 brownbear.png) 로 충돌 방지.

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
    object_key = f"sayeon/characters/{channel_id}/{filename}"
    return upload_image(
        file_path,
        object_key,
        bucket=bucket,
        public_base_url=public_base,
        content_type="image/png",
    )


def _character_bucket() -> str:
    return os.environ.get("R2_CHARACTER_BUCKET") or os.environ.get("R2_BUCKET", "videos")


def _character_public_base() -> str:
    return (
        os.environ.get("R2_CHARACTER_PUBLIC_BASE_URL")
        or os.environ.get("R2_PUBLIC_BASE_URL", "")
    ).rstrip("/")


def character_sheet_url(channel_id: str, filename: str = "sheet.png") -> str:
    """저장 규칙과 동일한 공개 URL(존재 확인 후 재사용용)."""
    return f"{_character_public_base()}/sayeon/characters/{channel_id}/{filename}"


def character_sheet_exists(channel_id: str, filename: str = "sheet.png") -> bool:
    """해당 키가 R2에 이미 있는지(head_object). 미설정/오류 시 False(→ 호출부가 생성)."""
    if not is_available():
        return False
    key = f"sayeon/characters/{channel_id}/{filename}"
    try:
        _get_client().head_object(Bucket=_character_bucket(), Key=key)
        return True
    except Exception:  # noqa: BLE001 - 없음/권한/네트워크 → 미존재로 처리
        return False


# ── 캐스트 아스펙트(멀티 아스펙트) — 역할별·아스펙트별 고정 키 ─────────────
# 키: cast/{role}/{aspect}.png  (채널 무관, 역할 스코프). 나중에 영상 씬 멀티레퍼런스가
# 읽을 규칙이므로 역할·아스펙트별 고정명을 유지한다. 캐릭터 시트와 같은 전용 버킷
# (R2_CHARACTER_BUCKET, Lifecycle 없음)을 쓴다.
def _cast_aspect_key(role: str, aspect: str) -> str:
    return f"cast/{role}/{aspect}.png"


def upload_cast_aspect(file_path: str, role: str, aspect: str) -> str:
    """캐스트 아스펙트 1장을 R2(cast/{role}/{aspect}.png)에 업로드하고 공개 URL 반환."""
    bucket = os.environ.get("R2_CHARACTER_BUCKET")
    public_base = os.environ.get("R2_CHARACTER_PUBLIC_BASE_URL")
    if not bucket:
        logger.warning(
            "R2_CHARACTER_BUCKET 미설정 — 기본 버킷 사용. 7일 Lifecycle 로 캐스트 시트가 "
            "삭제될 수 있으니 Lifecycle 없는 전용 버킷 설정을 권장합니다."
        )
    return upload_image(
        file_path,
        _cast_aspect_key(role, aspect),
        bucket=bucket,
        public_base_url=public_base,
        content_type="image/png",
    )


def cast_aspect_url(role: str, aspect: str) -> str:
    """저장 규칙과 동일한 공개 URL(존재 확인 후 재사용용)."""
    return f"{_character_public_base()}/{_cast_aspect_key(role, aspect)}"


def cast_aspect_exists(role: str, aspect: str) -> bool:
    """cast/{role}/{aspect}.png 가 R2에 이미 있는지. 미설정/오류 시 False."""
    if not is_available():
        return False
    try:
        _get_client().head_object(
            Bucket=_character_bucket(), Key=_cast_aspect_key(role, aspect)
        )
        return True
    except Exception:  # noqa: BLE001 - 없음/권한/네트워크 → 미존재로 처리
        return False


def list_cast_objects() -> dict[str, int]:
    """cast/ 프리픽스 아래 모든 오브젝트의 {키: LastModified epoch(int)} 맵.

    역할×아스펙트(8×7=56) head_object 대신 list_objects_v2 1~소수 회로 전체를 받아
    (a) 존재 멤버십 판정 + (b) 캐시 버스팅용 버전값(LastModified)을 함께 제공한다.
    LastModified 는 객체가 실제 덮어써질 때만 바뀌므로 ?v= 에 쓰면 불필요한 재다운로드가
    없다. 미설정/오류 시 빈 dict(호출부가 '없음'으로 처리).
    """
    if not is_available():
        return {}
    objs: dict[str, int] = {}
    try:
        client = _get_client()
        bucket = _character_bucket()
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="cast/"):
            for obj in page.get("Contents", []):
                lm = obj.get("LastModified")
                try:
                    epoch = int(lm.timestamp()) if lm is not None else 0
                except Exception:  # noqa: BLE001 - 이상값 → 버전 0
                    epoch = 0
                objs[obj["Key"]] = epoch
    except Exception:  # noqa: BLE001 - 권한/네트워크 → 빈 dict(없음 처리)
        return {}
    return objs
