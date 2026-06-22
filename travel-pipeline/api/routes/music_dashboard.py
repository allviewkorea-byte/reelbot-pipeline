"""음악 채널 대시보드 라우트 (prefix: /music) — 검토 대기 큐.

- GET  /music/queue                     : 검토 대기(pending) 목록
- POST /music/queue/{mix_id}/thumbnail  : 썸네일(base64) 업로드 → R2 + DB
- POST /music/queue/{mix_id}/publish    : 썸네일 게이트 → 유튜브 공개 업로드 → uploaded
- GET  /music/themes                    : 최근 주제 + 장르 팔레트(가이드 페이지용)

프론트(Next)는 proxyJson 으로 이 라우트를 호출한다. 썸네일은 멀티파트 대신
base64 JSON 으로 받아 프록시를 단순화한다(이미지가 작아 충분).
"""

from __future__ import annotations

import base64
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adapters import r2_storage
from services import music_theme, music_uploads

logger = logging.getLogger(__name__)

router = APIRouter()


def _with_thumb_url(row: dict) -> dict:
    """행에 thumbnail_url(있으면) 을 덧붙인다."""
    key = row.get("thumbnail_r2_key")
    slug, mix_id = row.get("slug") or "", row.get("mix_id") or ""
    if key and slug and mix_id:
        row = {**row, "thumbnail_url": r2_storage.music_thumbnail_url(slug, mix_id)}
    return row


@router.get("/queue")
def queue():
    """검토 대기(pending) 목록 — 최신순."""
    return {"queue": [_with_thumb_url(r) for r in music_uploads.list_pending()]}


class ThumbnailBody(BaseModel):
    image_base64: str  # data URL 또는 순수 base64
    slug: str | None = None


@router.post("/queue/{mix_id}/thumbnail")
def upload_thumbnail(mix_id: str, body: ThumbnailBody):
    """썸네일 업로드(base64) → R2 music-thumbnails/{slug}/{mix_id}.png → DB 키 저장."""
    row = music_uploads.get_upload(mix_id)
    if not row:
        raise HTTPException(status_code=404, detail="해당 mix_id 의 큐 항목이 없습니다.")
    slug = body.slug or row.get("slug") or ""
    if not slug:
        raise HTTPException(status_code=400, detail="slug 를 확인할 수 없습니다.")
    if not r2_storage.is_available():
        raise HTTPException(status_code=503, detail="R2 미설정 — 썸네일 저장 불가")

    raw = body.image_base64.split(",", 1)[-1]  # data URL 접두 제거
    try:
        data = base64.b64decode(raw)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"잘못된 base64 이미지: {e}") from e

    tmpdir = Path(tempfile.mkdtemp(prefix="thumb_"))
    try:
        png = tmpdir / "thumb.png"
        png.write_bytes(data)
        r2_storage.upload_music_thumbnail(str(png), slug, mix_id)
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    key = r2_storage.music_thumbnail_key(slug, mix_id)
    music_uploads.set_thumbnail(mix_id, key)
    return {"ok": True, "thumbnail_r2_key": key, "thumbnail_url": r2_storage.music_thumbnail_url(slug, mix_id)}


@router.post("/queue/{mix_id}/publish")
def publish(mix_id: str):
    """썸네일 게이트 → 유튜브 공개 업로드 → status=uploaded. 썸네일 없으면 400."""
    row = music_uploads.get_upload(mix_id)
    if not row:
        raise HTTPException(status_code=404, detail="해당 mix_id 의 큐 항목이 없습니다.")
    # ⛔ 게이트: 썸네일 없으면 공개 업로드 불가.
    if not row.get("thumbnail_r2_key"):
        raise HTTPException(status_code=400, detail="썸네일을 먼저 업로드하세요(공개 업로드 게이트).")

    slug = row.get("slug") or ""
    mp4_url = row.get("mp4_url")
    if not mp4_url:
        raise HTTPException(status_code=400, detail="영상(mp4_url)을 찾을 수 없습니다.")

    # 주제(메타데이터 풍부화) + 믹스(곡 목록) 복원.
    theme = music_theme.get_theme(slug) or {
        "slug": slug,
        "title_kr": row.get("title_kr"),
        "genre": row.get("genre"),
        "mood": row.get("mood"),
    }
    mix = {"mix_id": mix_id, "tracks": []}
    try:
        tmp_json = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}.json"
        r2_storage.download_music_object(
            r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp_json)
        )
        meta = json.loads(tmp_json.read_text(encoding="utf-8"))
        mix["tracks"] = meta.get("tracks") or []
    except Exception as e:  # noqa: BLE001 - 트랙 없으면 설명만 간소화
        logger.warning("[music-dashboard] 믹스 JSON 로드 실패(설명 간소화): %s", e)

    from services.youtube_upload import upload_music_video

    tmpdir = Path(tempfile.mkdtemp(prefix="pub_"))
    try:
        thumb = tmpdir / "thumb.png"
        try:
            r2_storage.download_music_object(row["thumbnail_r2_key"], str(thumb))
        except Exception as e:  # noqa: BLE001
            logger.warning("[music-dashboard] 썸네일 다운로드 실패(영상만 업로드): %s", e)
            thumb = None
        result = upload_music_video(
            mp4_url, theme, mix, privacy="public",
            thumbnail_path=(str(thumb) if thumb else None),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"유튜브 업로드 실패: {e}") from e
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    # upload_music_video 내부 record_upload 가 status=uploaded 로 마킹.
    return {"ok": True, "youtube_url": result["video_url"], "youtube_video_id": result["video_id"]}


# 가이드 페이지용 장르 팔레트(주제 헌법 §2 발췌, 읽기 전용).
_GENRE_PALETTE = [
    "시티팝", "피아노", "재즈", "로파이", "재즈힙합", "힙합", "R&B", "K-R&B",
    "소울/펑크", "빈티지 소울", "EDM/하우스", "신스웨이브", "보사노바",
    "어쿠스틱/포크", "앰비언트", "국악 퓨전", "클래식 크로스오버",
]


@router.get("/themes")
def themes():
    """가이드 페이지: 장르 팔레트 + 최근 주제 10개(읽기 전용)."""
    return {
        "palette": _GENRE_PALETTE,
        "recent": music_theme.list_recent_themes(10),
    }
