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


@router.get("/recent")
def recent_uploaded():
    """공개 업로드 완료 영상 최신순 — 대시보드 '최근 업로드' 마퀴용(썸네일 URL 동봉)."""
    return {"videos": [_with_thumb_url(r) for r in music_uploads.list_uploaded(12)]}


@router.delete("/queue/{mix_id}")
def delete_queue_item(mix_id: str):
    """큐에서 단일 영상 삭제(깨진/못 쓰는 영상 정리). 해당 mix_id 한 행만 영향.

    R2 mp4·썸네일 파일은 만료 정책에 맡기고 즉시 지우지 않는다(안전).
    """
    result = music_uploads.delete_pending(mix_id)
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return {"ok": True, "deleted": result.get("deleted", 0)}


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


def _load_mix(slug: str, mix_id: str) -> dict:
    """R2 믹스 JSON 복원 → {mix_id, mp3_url, tracks, total_sec, lyrics}."""
    mix = {"mix_id": mix_id, "tracks": [], "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3"),
           "total_sec": 0.0, "lyrics": ""}
    try:
        tmp_json = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}.json"
        r2_storage.download_music_object(r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp_json))
        meta = json.loads(tmp_json.read_text(encoding="utf-8"))
        mix["tracks"] = meta.get("tracks") or []
        mix["total_sec"] = float(meta.get("total_duration") or 0.0)
        mix["lyrics"] = "\n".join(
            (t.get("lyrics") or "").strip() for t in mix["tracks"] if (t.get("lyrics") or "").strip()
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-dashboard] 믹스 JSON 로드 실패: %s", e)
    return mix


def _build_localizations(theme: dict, viz_spec: dict | None, mix: dict) -> dict:
    """다국어 데이터 생성(번역 + 메타 + 해시태그). GPT 없으면 원본만(회귀 안전)."""
    from services import music_translate
    lyrics = mix.get("lyrics") or ""
    src = music_translate.detect_source_lang(lyrics or theme.get("title_kr", "") or "ko-")
    return {
        "source_lang": src,
        "meta": music_translate.generate_localizations(theme, viz_spec, lyrics),
        "lyrics": music_translate.translate_lyrics(lyrics, src) if lyrics.strip() else {},
        "hashtags": music_translate.generate_hashtags(theme, viz_spec),
    }


@router.post("/queue/{mix_id}/localize")
def localize_generate(mix_id: str):
    """다국어 데이터 생성(또는 캐시 반환) — 검수 UI [다국어 ▼] 진입 시 호출. {ok, localizations}."""
    row = music_uploads.get_upload(mix_id)
    if not row:
        raise HTTPException(status_code=404, detail="해당 mix_id 의 큐 항목이 없습니다.")
    cached = row.get("localizations")
    if isinstance(cached, dict) and cached.get("meta"):
        return {"ok": True, "localizations": cached, "cached": True}
    slug = row.get("slug") or ""
    theme = music_theme.get_theme(slug) or {
        "slug": slug, "title_kr": row.get("title_kr"), "genre": row.get("genre"), "mood": row.get("mood"),
    }
    mix = _load_mix(slug, mix_id)
    loc = _build_localizations(theme, row.get("viz_spec"), mix)
    music_uploads.set_localizations(mix_id, loc)
    return {"ok": True, "localizations": loc, "cached": False}


class LocalizationsBody(BaseModel):
    localizations: dict


@router.put("/queue/{mix_id}/localize")
def localize_save(mix_id: str, body: LocalizationsBody):
    """검수 UI 에서 수정한 다국어 데이터 저장. {ok}."""
    res = music_uploads.set_localizations(mix_id, body.localizations)
    if res.get("error"):
        raise HTTPException(status_code=502, detail=res["error"])
    return {"ok": True}


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
    # 믹스 복원 — make_video 가 mp3 를 받아야 하므로 mp3_url 도 구성.
    mix = {
        "mix_id": mix_id,
        "tracks": [],
        "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3"),
    }
    try:
        tmp_json = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}.json"
        r2_storage.download_music_object(
            r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp_json)
        )
        meta = json.loads(tmp_json.read_text(encoding="utf-8"))
        mix["tracks"] = meta.get("tracks") or []
    except Exception as e:  # noqa: BLE001 - 트랙 없으면 설명만 간소화
        logger.warning("[music-dashboard] 믹스 JSON 로드 실패(설명 간소화): %s", e)

    from services.music_video import make_video
    from services.youtube_upload import upload_music_video

    tmpdir = Path(tempfile.mkdtemp(prefix="pub_"))
    try:
        # 1) 썸네일 다운로드(게이트로 존재 보장 — 실패 시 진행 불가).
        thumb = tmpdir / "thumb.png"
        try:
            r2_storage.download_music_object(row["thumbnail_r2_key"], str(thumb))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"썸네일 다운로드 실패: {e}") from e

        # 2) 깨끗한 이미지를 배경으로 영상 재생성 → 새 mp4(R2). Remotion 이 인트로·텍스트·이퀄 합성.
        vres = make_video(theme, mix, background_path=str(thumb))
        new_mp4_url = vres["video_url"]

        # 3) 유튜브 썸네일 = 영상 첫 프레임(#20, Remotion 텍스트 포함) — 있으면 다운로드해 사용,
        #    없으면(폴백 렌더) 대표가 올린 이미지로.
        yt_thumb = str(thumb)
        frame_key = vres.get("frame_thumb_key")
        if frame_key:
            try:
                frame_png = tmpdir / "frame.png"
                r2_storage.download_music_object(frame_key, str(frame_png))
                yt_thumb = str(frame_png)
            except Exception as e:  # noqa: BLE001 - 실패 시 업로드 이미지로 폴백
                logger.warning("[music-dashboard] 첫프레임 썸네일 다운로드 실패(업로드본 사용): %s", e)

        # 4) 재생성 mp4 + 썸네일 set 으로 공개 업로드.
        result = upload_music_video(
            new_mp4_url, theme, mix, privacy="public", thumbnail_path=yt_thumb,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"공개 업로드(재생성) 실패: {e}") from e
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    # 5) #32 다국어 — 제목·설명 localizations + 자막(captions) 적용(best-effort, 실패해도 영상은 공개됨).
    ml = {"localizations": {"ok": False}, "captions": {}}
    try:
        from services.youtube_upload import set_localizations, upload_captions
        from services import music_subtitles
        loc = music_uploads.get_localizations(mix_id) or _build_localizations(theme, row.get("viz_spec"), mix)
        vid = result["video_id"]
        meta = loc.get("meta") or {}
        if meta:
            ml["localizations"] = set_localizations(vid, meta, default_lang=loc.get("source_lang", "ko"))
        lyrics_by_lang = loc.get("lyrics") or {}
        if lyrics_by_lang and mix.get("tracks"):
            total = mix.get("total_sec") or 0.0
            srt = music_subtitles.build_srt_by_lang(mix["tracks"], total, lyrics_by_lang)
            ml["captions"] = upload_captions(vid, srt)
    except Exception as e:  # noqa: BLE001 - 다국어 실패는 영상 공개를 막지 않음
        logger.warning("[music-dashboard] 다국어 적용 실패(영상은 공개됨): %s", e)

    # upload_music_video 내부 record_upload 가 status=uploaded 로 마킹.
    return {"ok": True, "youtube_url": result["video_url"], "youtube_video_id": result["video_id"], "multilang": ml}


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
