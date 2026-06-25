"""유튜브 업로드 서비스 — YouTube Data API v3 videos.insert + thumbnails.set.

사연 영상(mp4) + 썸네일(png) 을 채널에 업로드한다. 제목은 썸네일 카피, 설명은 대본
요약 + 고정 푸터/해시태그, 태그는 고정 리스트. 기본 공개(public), 아동용 아님,
카테고리 22(사람/블로그), 기본 언어 ko.

자격증명은 youtube_oauth.get_credentials()(refresh_token 기반, 자동 갱신).
googleapiclient import 는 함수 안에서 지연 로딩(미설치 환경 import 안전).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import traceback
from pathlib import Path

# 영상/썸네일 다운로드는 검증된 합성 엔진 헬퍼 재사용(http URL/로컬 경로 모두 처리).
from services.sayeon_assemble import _fetch
from services.youtube_oauth import get_credentials, is_connected

logger = logging.getLogger(__name__)

# 고정 태그(작업지시서).
DEFAULT_TAGS = ["실화", "사연", "공감", "백곰", "실화사연", "숏폼", "실화보고서"]

_SHORTS_TAG = "#Shorts"

# 설명 푸터(제보 줄 제거). 마지막 해시태그 줄에 #Shorts 포함.
_DESC_FOOTER = (
    "매일 새 실화 업로드\n\n"
    "#실화 #사연 #공감 #백곰 #실화사연 #숏폼 #백곰의실화보고서 #Shorts"
)


def _summarize(script: str, max_sentences: int = 3) -> str:
    """대본 첫 2~3문장 요약."""
    text = " ".join(line.strip() for line in (script or "").splitlines() if line.strip())
    if not text:
        return ""
    sentences = re.split(r"(?<=[.?!…])\s+", text)
    summary = " ".join(s for s in sentences[:max_sentences] if s).strip()
    return summary or text[:120]


def build_video_metadata(hook_text: str, script: str) -> tuple[str, str, list[str]]:
    """(제목, 설명, 태그). 제목=썸네일 카피, 설명=요약+푸터, 태그=고정."""
    title = " ".join((hook_text or "").replace("\\n", "\n").split())
    if not title:
        title = _summarize(script, 1)[:40]
    # 제목 끝에 #Shorts 자동 추가(유튜브 제목 100자 한도 내에서 공간 확보).
    if _SHORTS_TAG.lower() not in title.lower():
        title = f"{title[: 100 - len(_SHORTS_TAG) - 1].rstrip()} {_SHORTS_TAG}"
    title = title[:100]
    summary = _summarize(script)
    description = f"{summary}\n\n{_DESC_FOOTER}" if summary else _DESC_FOOTER
    return title, description, list(DEFAULT_TAGS)


def _target_channel_id() -> str:
    return (os.getenv("YOUTUBE_CHANNEL_ID") or "").strip()


def _content_owner() -> str:
    """CMS(콘텐츠 소유자) ID. 설정 시에만 onBehalfOfContentOwner 경로 사용(파트너 전용)."""
    return (os.getenv("YOUTUBE_CONTENT_OWNER_ID") or "").strip()


def _verify_channel(youtube) -> None:
    """OAuth 토큰이 가리키는 실제 업로드 채널을 확인·로깅하고, 목표와 다르면 차단한다.

    ⚠️ videos.insert 는 '인증된 토큰의 채널'에만 업로드된다(snippet.channelId 로 임의
    채널을 지정해도 무시됨). 따라서 브랜드 채널 업로드는 OAuth 인증 시 그 채널을
    선택해야 한다. 여기서는 토큰의 채널을 조회해 YOUTUBE_CHANNEL_ID 와 비교하고,
    다르면 개인 채널로 잘못 올라가지 않도록 명확한 오류로 막는다(재인증 안내).
    """
    target = _target_channel_id()
    try:
        resp = youtube.channels().list(part="id,snippet", mine=True).execute()
        items = resp.get("items", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("[youtube-debug] 채널 확인 실패(업로드는 계속): %s", e)
        return
    if not items:
        logger.warning("[youtube-debug] 인증 토큰에 연결된 채널이 없습니다.")
        return
    actual_id = items[0].get("id", "")
    actual_title = items[0].get("snippet", {}).get("title", "")
    logger.warning(
        "[youtube-debug] 인증 채널: id=%s title=%s (목표 YOUTUBE_CHANNEL_ID=%s)",
        actual_id, actual_title, target or "(미설정)",
    )
    if target and actual_id != target:
        raise RuntimeError(
            f"업로드 대상 채널 불일치: 토큰 채널={actual_id}({actual_title}) ≠ "
            f"YOUTUBE_CHANNEL_ID={target}. 브랜드 채널('백곰의 실화보고서')로 올리려면 "
            "/api/youtube/auth 재인증 시 해당 브랜드 채널을 선택하세요. "
            "(videos.insert 는 토큰 채널에만 업로드되며 channelId 임의 지정은 불가)"
        )


def upload_video(
    video_path: str,
    title: str,
    description: str,
    thumbnail_path: str | None = None,
    tags: list[str] | None = None,
    privacy: str | None = None,
    synthetic_media: bool | None = None,
) -> dict:
    """영상 1개를 업로드하고 (가능하면) 썸네일을 첨부. Returns {video_id, video_url}.

    업로드 채널은 OAuth 토큰의 채널로 고정된다. 일반 계정은 _verify_channel 로 목표
    채널(YOUTUBE_CHANNEL_ID) 일치를 검증하고, CMS(YOUTUBE_CONTENT_OWNER_ID) 설정 시에는
    onBehalfOfContentOwner(+Channel)로 소유 채널에 업로드한다(파트너 전용 경로).
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"업로드할 영상 파일 없음: {video_path}")

    # 자격증명/클라이언트 생성(WARNING 레벨로 가시성 확보).
    logger.warning("[youtube-debug] 자격증명/클라이언트 생성 시작")
    try:
        creds = get_credentials()
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("[youtube-debug] 자격증명/클라이언트 생성 실패: %s\n%s", e, traceback.format_exc())
        raise
    logger.warning("[youtube-debug] 자격증명/클라이언트 생성 완료")

    owner = _content_owner()
    if not owner:
        # 일반 계정: 토큰 채널이 목표 브랜드 채널인지 검증(아니면 차단).
        _verify_channel(youtube)

    # 우선순위: 명시 인자(채널 모드) > env(YOUTUBE_PRIVACY_STATUS) > 'public'.
    privacy = (privacy or os.getenv("YOUTUBE_PRIVACY_STATUS") or "public").strip().lower()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or list(DEFAULT_TAGS),
            "categoryId": "22",          # 사람 및 블로그
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy,    # 기본 public (테스트 시 YOUTUBE_PRIVACY_STATUS=private)
            "selfDeclaredMadeForKids": False,
        },
    }
    # ⑫/⑬ AI/합성 콘텐츠 표시. 우선순위: 전달 인자(채널 토글) > env(YOUTUBE_SYNTHETIC_MEDIA)
    # > False. on 이면 status.containsSyntheticMedia=True(YouTube Data API v3, 2024.10.30~),
    # 아니면 필드 미포함(기존 동작). 만화체라 의무는 아니나 투명성 위해 옵트인.
    if synthetic_media is None:
        synthetic = (os.getenv("YOUTUBE_SYNTHETIC_MEDIA") or "").strip().lower() in (
            "1", "true", "on", "yes",
        )
    else:
        synthetic = bool(synthetic_media)
    if synthetic:
        body["status"]["containsSyntheticMedia"] = True
    logger.warning("[youtube-debug] containsSyntheticMedia=%s", synthetic)
    # CMS 경로(파트너): 콘텐츠 소유자 권한으로 특정 소유 채널에 업로드.
    insert_kwargs: dict = {"part": "snippet,status", "body": body}
    if owner:
        insert_kwargs["onBehalfOfContentOwner"] = owner
        if _target_channel_id():
            insert_kwargs["onBehalfOfContentOwnerChannel"] = _target_channel_id()
        logger.warning(
            "[youtube-debug] CMS 업로드 경로: contentOwner=%s channel=%s",
            owner, _target_channel_id(),
        )

    logger.warning(
        "[youtube-debug] 유튜브 API 업로드 시작: privacy=%s file=%s", privacy, video_path
    )
    try:
        media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=-1, resumable=True)
        request = youtube.videos().insert(media_body=media, **insert_kwargs)
        response = request.execute()
    except Exception as e:  # noqa: BLE001
        logger.warning("[youtube-debug] videos.insert 실패: %s\n%s", e, traceback.format_exc())
        raise
    video_id = response["id"]
    logger.warning("[youtube-debug] 유튜브 업로드 성공: video_id=%s privacy=%s", video_id, privacy)

    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            thumb_kwargs: dict = {"videoId": video_id,
                                  "media_body": MediaFileUpload(thumbnail_path, mimetype="image/png")}
            if owner:
                thumb_kwargs["onBehalfOfContentOwner"] = owner
            youtube.thumbnails().set(**thumb_kwargs).execute()
            logger.warning("[youtube-debug] 썸네일 첨부 완료: video_id=%s", video_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[youtube-debug] 썸네일 첨부 실패(영상은 업로드됨): %s\n%s", e, traceback.format_exc())

    return {"video_id": video_id, "video_url": f"https://www.youtube.com/watch?v={video_id}"}


# ── 음악 채널(Revezen) 재생목록 자동 분류 — 장르 → 재생목록 매핑 ──────────────
# 5개 묶음(드라이브·카페·늦은밤·에너지·휴식). 재생목록 ID 가 바뀔 때를 대비해
# Railway 환경변수(PLAYLIST_DRIVE/CAFE/LATENIGHT/ENERGY/REST)로 오버라이드 가능.
def _pl(env_key: str, default: str) -> str:
    return (os.getenv(env_key) or default).strip()


def _playlist_map() -> dict[str, str]:
    drive = _pl("PLAYLIST_DRIVE", "PLZrNOKwpF4k0")
    cafe = _pl("PLAYLIST_CAFE", "PLcNZY43Ms0_E")
    latenight = _pl("PLAYLIST_LATENIGHT", "PLJ4wcfQLMbKQ")
    energy = _pl("PLAYLIST_ENERGY", "PLT7NryPLY43s")
    rest = _pl("PLAYLIST_REST", "PLTjRC7ZWEzhs")
    return {
        # 드라이브
        "citypop": drive, "sunset_drive": drive, "morning_drive": drive,
        # 카페
        "cafe": cafe, "cafe_bgm": cafe, "lofi": cafe,
        # 늦은 밤
        "jazz": latenight, "rnb_soul": latenight, "ballad": latenight,
        "breakup": latenight, "bar_lounge": latenight,
        # 에너지
        "workout": energy, "kpop": energy, "pop": energy, "hiphop": energy,
        # 휴식
        "sleep_study": rest, "spa_meditation": rest, "library_study": rest,
        "hotel_lobby": rest,
    }


def add_to_playlist(youtube, video_id: str, playlist_id: str) -> bool:
    """업로드된 영상을 재생목록에 추가(playlistItems.insert). 실패해도 업로드는 성공으로 처리."""
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id,
                    },
                }
            },
        ).execute()
        return True
    except Exception as e:  # noqa: BLE001 - 재생목록 추가 실패는 업로드를 막지 않음
        logger.warning(
            "[playlist] 재생목록 추가 실패 (video=%s, playlist=%s): %s",
            video_id, playlist_id, e,
        )
        return False


def _genre_playlist_id(theme: dict) -> str | None:
    """주제 → 장르 id → 재생목록 id. genre_id 우선, 없으면 분류(best-effort). 매핑 없으면 None."""
    from services import music_genres
    genre_id = (theme.get("genre_id") or music_genres.classify_theme(theme) or "").strip().lower()
    return _playlist_map().get(genre_id)


# ── 음악 채널(Revezen) 업로드 — 백곰과 분리, additive ──────────────────────
def build_music_metadata(theme: dict, mix: dict) -> tuple[str, str, list[str]]:
    """음악 영상 메타데이터 (제목, 설명, 태그).

    제목: '{title_kr} | {genre} Mix'
    설명: 장르·상황·무드 + 곡 목록(mix 오프셋 기반, mm:ss).
    태그: 장르·상황·무드(키워드) + style_prompt 영어 토큰 + 일반 음악 태그.
    """
    title_kr = (theme.get("title_kr") or theme.get("title") or "").strip()
    genre = (theme.get("genre") or "").strip()
    situation = (theme.get("situation") or "").strip()
    mood = (theme.get("mood") or "").strip()

    title = f"{title_kr} | {genre} Mix".strip(" |") if genre else title_kr
    title = title[:100]

    # 설명: 첫 줄 요약(장르·상황·무드) + 곡 목록 타임스탬프.
    head_bits = [b for b in (genre, situation, mood) if b]
    head = " · ".join(head_bits)
    lines = [head] if head else []
    tracks = mix.get("tracks") or []
    if tracks:
        lines.append("")
        lines.append("🎵 Tracklist")
        for t in tracks:
            start = float(t.get("start_sec") or 0.0)
            mm, ss = divmod(int(start), 60)
            name = (t.get("title") or "").strip()
            if name:
                lines.append(f"{mm:02d}:{ss:02d} {name}")
    description = "\n".join(lines).strip()

    # 태그: 한국어 키워드 + style_prompt 영어 토큰 + 일반.
    tags: list[str] = []
    for kw in (genre, situation, mood):
        for part in re.split(r"[·,/]", kw or ""):
            part = part.strip()
            if part and part not in tags:
                tags.append(part)
    for tok in re.split(r"[,\n]", theme.get("style_prompt") or ""):
        tok = tok.strip()
        if tok and len(tok) <= 30 and tok not in tags:
            tags.append(tok)
    for generic in ("music", "playlist", "mix", "Rooftop Music"):
        if generic not in tags:
            tags.append(generic)
    return title, description, tags[:30]


def _verify_music_channel(youtube) -> None:
    """업로드 토큰 채널이 음악 채널 ID 와 일치하는지 검증(불일치 시 차단).

    음악 채널 ID 는 YOUTUBE_CHANNEL_ID_MUSIC 우선, 미설정 시 YOUTUBE_CHANNEL_ID 로 폴백.
    """
    target = (os.getenv("YOUTUBE_CHANNEL_ID_MUSIC") or os.getenv("YOUTUBE_CHANNEL_ID") or "").strip()
    try:
        resp = youtube.channels().list(part="id,snippet", mine=True).execute()
        items = resp.get("items", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-youtube] 채널 확인 실패(업로드는 계속): %s", e)
        return
    if not items:
        logger.warning("[music-youtube] 인증 토큰에 연결된 채널이 없습니다.")
        return
    actual_id = items[0].get("id", "")
    actual_title = items[0].get("snippet", {}).get("title", "")
    logger.warning(
        "[music-youtube] 인증 채널: id=%s title=%s (목표=%s)",
        actual_id, actual_title, target or "(미설정)",
    )
    if target and actual_id != target:
        raise RuntimeError(
            f"음악 업로드 대상 채널 불일치: 토큰 채널={actual_id}({actual_title}) ≠ "
            f"YOUTUBE_CHANNEL_ID_MUSIC={target}. /api/music/youtube/auth 재인증 시 "
            "Revezen 채널을 선택하세요."
        )


def upload_music_video(
    mp4_path: str,
    theme: dict,
    mix: dict,
    *,
    privacy: str = "private",
    thumbnail_path: str | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """음악 영상(mp4)을 음악 채널(Revezen)에 업로드. Returns {video_id, video_url}.

    백곰 upload_video 와 분리: 음악 OAuth(music_youtube_oauth.get_credentials),
    카테고리 10(음악). privacy 기본 'private'(검토 큐), 대시보드 공개 시 'public'.
    thumbnail_path 가 있으면 썸네일도 첨부. mp4_path 는 R2 URL/로컬 경로 모두 가능.
    title/description/tags 를 주면(#37 풍부화 메타) 그것을 쓰고, 없으면 build_music_metadata.
    업로드 성공 시 music_uploads 에 기록(실패해도 업로드는 성공).
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from services.music_uploads import record_upload
    from services.music_youtube_oauth import get_credentials as music_get_credentials

    d_title, d_desc, d_tags = build_music_metadata(theme, mix)
    title = title or d_title
    description = description or d_desc
    tags = tags or d_tags
    privacy = (privacy or "private").strip().lower()

    with tempfile.TemporaryDirectory(prefix="ytmusic_") as tmp:
        local = Path(tmp) / "video.mp4"
        _fetch(mp4_path, local)  # URL/로컬 모두 처리
        if not local.exists() or local.stat().st_size == 0:
            raise FileNotFoundError(f"업로드할 음악 영상 없음/빈 파일: {mp4_path}")

        creds = music_get_credentials()
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        _verify_music_channel(youtube)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "10",        # 음악
                "defaultLanguage": "ko",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        logger.warning("[music-youtube] 업로드 시작: title=%s privacy=%s", title, privacy)
        media = MediaFileUpload(str(local), mimetype="video/mp4", chunksize=-1, resumable=True)
        response = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.warning("[music-youtube] 업로드 성공: video_id=%s", video_id)

        # 썸네일 첨부(있으면). 실패해도 영상은 업로드됨.
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
                ).execute()
                logger.warning("[music-youtube] 썸네일 첨부 완료: video_id=%s", video_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("[music-youtube] 썸네일 첨부 실패(영상은 업로드됨): %s", e)

        # 재생목록 자동 분류 — 장르 매핑이 있으면 해당 재생목록에 추가(best-effort).
        # 매핑 없는 장르 → 추가 없이 그냥 업로드. 어떤 실패도 업로드를 막지 않음.
        try:
            playlist_id = _genre_playlist_id(theme)
            if playlist_id and add_to_playlist(youtube, video_id, playlist_id):
                logger.warning(
                    "[playlist] 재생목록 추가 완료: video=%s playlist=%s", video_id, playlist_id
                )
        except Exception as e:  # noqa: BLE001 - 재생목록 분류 실패는 업로드를 막지 않음
            logger.warning("[playlist] 재생목록 분류 단계 실패(영상은 업로드됨): %s", e)

    # 기록(best-effort).
    try:
        record_upload(
            theme.get("slug") or theme.get("theme_slug") or "",
            mix.get("mix_id") or "",
            video_id,
            video_url,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-youtube] 업로드 기록 실패(영상은 업로드됨): %s", e)

    return {"video_id": video_id, "video_url": video_url}


def publish_to_youtube(
    video_url: str, thumbnail_url: str, hook_text: str, script: str,
    privacy: str | None = None, synthetic_media: bool | None = None,
) -> dict:
    """완성 영상(URL/로컬) + 썸네일 → 메타데이터 생성 → 업로드. Returns {video_id, video_url}.

    오케스트레이터가 호출. video_url/thumbnail_url 은 R2 URL 또는 로컬 경로 모두 가능
    (_fetch 가 처리). 임시 디렉터리에 받아 업로드한다.
    """
    logger.warning("[youtube-debug] publish_to_youtube 진입")
    connected = is_connected()
    logger.warning("[youtube-debug] is_connected=%s", connected)
    title, description, tags = build_video_metadata(hook_text, script)
    with tempfile.TemporaryDirectory(prefix="yt_") as tmp:
        tmp_dir = Path(tmp)
        local_video = tmp_dir / "video.mp4"
        logger.warning("[youtube-debug] R2 영상 다운로드 시작: %s", video_url)
        try:
            _fetch(video_url, local_video)
        except Exception as e:  # noqa: BLE001
            logger.warning("[youtube-debug] 영상 다운로드 실패: %s\n%s", e, traceback.format_exc())
            raise
        size = local_video.stat().st_size if local_video.exists() else 0
        logger.warning("[youtube-debug] R2 영상 다운로드 완료: %d bytes", size)

        local_thumb: str | None = None
        if thumbnail_url:
            try:
                t = tmp_dir / "thumb.png"
                logger.warning("[youtube-debug] 썸네일 다운로드 시작: %s", thumbnail_url)
                _fetch(thumbnail_url, t)
                local_thumb = str(t)
                logger.warning("[youtube-debug] 썸네일 다운로드 완료")
            except Exception as e:  # noqa: BLE001
                logger.warning("[youtube-debug] 썸네일 다운로드 실패(영상만 업로드): %s\n%s", e, traceback.format_exc())

        try:
            result = upload_video(
                str(local_video), title, description, local_thumb, tags,
                privacy=privacy, synthetic_media=synthetic_media,
            )
            logger.warning("[youtube-debug] 업로드 성공: %s", result.get("video_url"))
            return result
        except Exception as e:  # noqa: BLE001
            logger.warning("[youtube-debug] 업로드 실패: %s\n%s", e, traceback.format_exc())
            raise


# ── #32 다국어: 자막(captions) + 제목·설명(localizations) ────────────────
def _music_youtube_client():
    """음악 채널 YouTube 클라이언트(force-ssl 포함 스코프 필요)."""
    from googleapiclient.discovery import build
    from services.music_youtube_oauth import get_credentials as music_get_credentials
    creds = music_get_credentials()
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_captions(video_id: str, srt_by_lang: dict[str, str]) -> dict:
    """언어별 SRT 를 자막 트랙으로 업로드(captions.insert). {uploaded:[lang...], failed:{lang:err}}.

    force-ssl 스코프 필요(재인증). 실패는 언어별로 격리(한 언어 실패가 나머지 막지 않음).
    """
    import tempfile
    from pathlib import Path
    from googleapiclient.http import MediaFileUpload

    uploaded: list[str] = []
    failed: dict[str, str] = {}
    if not srt_by_lang:
        return {"uploaded": [], "failed": {}}
    youtube = _music_youtube_client()
    with tempfile.TemporaryDirectory(prefix="srt_") as tmp:
        for lang, srt in srt_by_lang.items():
            if not (srt or "").strip():
                continue
            try:
                path = Path(tmp) / f"{lang}.srt"
                path.write_text(srt, encoding="utf-8")
                body = {"snippet": {"videoId": video_id, "language": lang, "name": lang, "isDraft": False}}
                media = MediaFileUpload(str(path), mimetype="application/octet-stream", resumable=False)
                youtube.captions().insert(part="snippet", body=body, media_body=media).execute()
                uploaded.append(lang)
            except Exception as e:  # noqa: BLE001 - 언어별 격리
                failed[lang] = str(e)[:200]
                logger.warning("[music-youtube] 자막 업로드 실패(%s): %s", lang, e)
    logger.warning("[music-youtube] 자막 %d개 업로드(실패 %d)", len(uploaded), len(failed))
    return {"uploaded": uploaded, "failed": failed}


def set_localizations(video_id: str, localizations: dict[str, dict], default_lang: str = "ko") -> dict:
    """제목·설명 다국어 적용(videos.update localizations). {ok, error}.

    localizations: {lang: {title, description}}. 기존 snippet 보존 + defaultLanguage 설정.
    """
    if not localizations:
        return {"ok": False, "error": "localizations 비어있음"}
    try:
        youtube = _music_youtube_client()
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return {"ok": False, "error": "영상을 찾을 수 없음"}
        snippet = items[0]["snippet"]
        snippet["defaultLanguage"] = default_lang
        loc = {
            lng: {"title": str(d.get("title", ""))[:100], "description": str(d.get("description", ""))}
            for lng, d in localizations.items()
            if isinstance(d, dict) and d.get("title")
        }
        youtube.videos().update(
            part="snippet,localizations",
            body={"id": video_id, "snippet": snippet, "localizations": loc},
        ).execute()
        logger.warning("[music-youtube] localizations %d개 언어 적용", len(loc))
        return {"ok": True, "error": None}
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-youtube] localizations 실패: %s", e)
        return {"ok": False, "error": str(e)[:200]}
