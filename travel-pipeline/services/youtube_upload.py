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


_PLAYLISTS = {
    "sleep": lambda: _pl("PLAYLIST_SLEEP", "PLfINU1S2uFfo"),
    "focus": lambda: _pl("PLAYLIST_FOCUS", "PLNIiY6A05fMM"),
    "drive": lambda: _pl("PLAYLIST_DRIVE", "PLZrNOKwpF4k0"),
    "cafe": lambda: _pl("PLAYLIST_CAFE", "PLcNZY43Ms0_E"),
    "cafe_bgm": lambda: _pl("PLAYLIST_CAFE_BGM", "PLXynadl7wJfY"),
    "energy": lambda: _pl("PLAYLIST_ENERGY", "PLT7NryPLY43s"),
    "rest": lambda: _pl("PLAYLIST_REST", "PLNyKKy7h1SHc"),
    "romance": lambda: _pl("PLAYLIST_ROMANCE", "PLeNMP0Qqclic"),
    "latenight": lambda: _pl("PLAYLIST_LATENIGHT", "PLJ4wcfQLMbKQ"),
    "travel": lambda: _pl("PLAYLIST_TRAVEL", "PLGOCcTR2EIxM"),
    "comfort": lambda: _pl("PLAYLIST_COMFORT", "PLE-mN861qjiE"),
    "energyboost": lambda: _pl("PLAYLIST_ENERGYBOOST", "PLRB22-HZL9h0"),
}


def _get_playlist(key: str) -> str:
    return _PLAYLISTS[key]()


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
    """tag_combo 8축 기반 12개 재생목록 매칭. 매칭 안 되면 None(재생목록 미배정)."""
    combo = theme.get("tag_combo")
    if not combo:
        return _legacy_playlist(theme)

    action = combo.get("action") or ""
    genres = combo.get("genre") or []
    if isinstance(genres, str):
        genres = [genres]
    situations = combo.get("situation") or []
    if isinstance(situations, str):
        situations = [situations]
    emotions = combo.get("emotion") or []
    if isinstance(emotions, str):
        emotions = [emotions]
    formats = combo.get("format") or []
    if isinstance(formats, str):
        formats = [formats]

    genres_s = set(genres)
    situations_s = set(situations)
    emotions_s = set(emotions)

    _INSTRUMENTAL_FORMATS = {"instrumental", "piano_solo", "guitar_solo", "inst_only", "beats_only", "nature_mix", "nature_only"}
    is_inst = bool(set(formats) & _INSTRUMENTAL_FORMATS)

    # where 설계 원칙: 사람들은 '뭐 할 때(action)'로 검색한다 → action이 주축.
    # action이 있고 매칭되면 action이 이긴다. genre/situation/emotion 규칙은
    # action이 없거나 매칭 실패했을 때만 작동하는 폴백이다.
    _FOCUS = {"study", "focus", "coding", "reading"}
    _DRIVE = {"drive", "drive_scenic", "commute_morning", "commute_evening"}
    _ENERGY = {"workout", "running", "cleaning", "startup"}
    _REST = {"rest", "yoga", "stretching", "pilates", "zone_out"}
    _ROMANCE = {"date", "couple", "singing"}
    _SLEEP = {"sleep", "baby_sleep", "meditation"}

    # 우선순위 1 — 카페 (action 기준 + 형식 분기)
    if action in ("cafe", "walk"):
        return _get_playlist("cafe_bgm") if is_inst else _get_playlist("cafe")

    # 우선순위 2 — action 직접 매칭
    if action in _FOCUS:
        return _get_playlist("focus")
    if action in _DRIVE:
        return _get_playlist("drive")
    if action in _ENERGY:
        return _get_playlist("energy")
    if action in _REST:
        return _get_playlist("rest")
    if action in _ROMANCE:
        return _get_playlist("romance")
    if action in _SLEEP:
        return _get_playlist("sleep")
    if action == "travel":
        return _get_playlist("travel")

    # 우선순위 3 — 에너지 부스트 (action = confidence)
    if action == "confidence":
        return _get_playlist("energyboost")

    # 우선순위 4 — 발라드/이별 (action 미매칭 폴백)
    if genres_s & {"ballad", "kballad", "sensballad"} or situations_s & {"breakup", "lights_off"}:
        return _get_playlist("latenight")

    # 우선순위 5 — 위로 (action 미매칭 폴백)
    if emotions_s & {"lonely", "sad", "depressed", "desolate", "comfort"} or situations_s & {"alone", "rain", "cloudy"}:
        return _get_playlist("comfort")

    # 우선순위 6 — 에너지 부스트 (emotion 기준 폴백)
    if emotions_s & {"hopeful", "passionate", "positive", "excited", "refreshed"}:
        return _get_playlist("energyboost")

    # 우선순위 7 — 설렘 보조 (emotion 기준 폴백)
    if emotions_s & {"excited", "heartbeat"}:
        return _get_playlist("romance")

    return None


def _legacy_playlist(theme: dict) -> str | None:
    """tag_combo 없는 옛날 14장르 영상용 폴백. classify_theme → 12개 매핑."""
    from services import music_genres
    genre_id = (theme.get("genre_id") or music_genres.classify_theme(theme) or "").strip().lower()
    _LEGACY_MAP = {
        "citypop": "drive", "sunset_drive": "drive", "morning_drive": "drive",
        "cafe": "cafe", "cafe_bgm": "cafe", "lofi": "cafe",
        "jazz": "latenight", "rnb_soul": "latenight", "ballad": "latenight",
        "breakup": "latenight", "bar_lounge": "latenight",
        "workout": "energy", "kpop": "energy", "pop": "energy", "hiphop": "energy",
        "sleep_study": "sleep", "spa_meditation": "rest", "library_study": "focus",
        "hotel_lobby": "rest",
    }
    pl_key = _LEGACY_MAP.get(genre_id)
    return _get_playlist(pl_key) if pl_key else None


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


def _verify_music_channel(youtube, channel: str | None = None) -> None:
    """업로드 토큰 채널이 목표 채널 ID 와 일치하는지 검증(불일치 시 차단).

    ★ 비대칭 설계 — 의도적이다.

    where(기본, channel=None)는 **기존 동작 그대로**: 확인 실패·연결 채널 없음·env
    미설정이면 경고만 남기고 통과한다. 지금까지 이 상태로 운영됐고 회귀 0 이 우선이다.
    목표 ID 는 YOUTUBE_CHANNEL_ID_MUSIC 우선, 미설정 시 백곰 YOUTUBE_CHANNEL_ID 폴백
    (논리적으론 이상하지만 제거하면 동작이 바뀌므로 유지).

    채널을 **명시한 경우**(운동 등)는 아래 넷을 전부 거부한다. 확인이 안 되면 올리지
    않는다 — 운동 곡이 where 에 공개되면 되돌리려면 삭제해야 하고 그 사이 구독자가 본다.
    조용히 다른 채널로 올라가는 것이 최악의 사고다.
      ① 해당 채널의 채널ID env 없음   (기존엔 target="" 이라 검증 자체가 스킵됐다)
      ② channels().list API 호출 실패 (기존엔 통과)
      ③ 연결된 채널 없음(items 빈 값) (기존엔 통과)
      ④ 채널 불일치                    (기존에도 차단)
    명시 채널은 백곰 env 로 폴백하지 않는다 — 자기 env 만 본다.
    """
    from services import music_youtube_oauth as _mo

    strict = channel is not None
    if strict:
        env_key = _mo.channel_id_env_key(channel)
        target = _mo.configured_channel_id(channel)  # 폴백 없음
        if not target:
            raise RuntimeError(
                f"[업로드 거부] env 없음 — {env_key} 가 설정되지 않았습니다(channel={channel}). "
                "채널 ID 를 넣기 전에는 업로드할 수 없습니다(다른 채널로 잘못 올라가는 것을 막습니다)."
            )
    else:
        target = (
            os.getenv("YOUTUBE_CHANNEL_ID_MUSIC") or os.getenv("YOUTUBE_CHANNEL_ID") or ""
        ).strip()

    try:
        resp = youtube.channels().list(part="id,snippet", mine=True).execute()
        items = resp.get("items", [])
    except Exception as e:  # noqa: BLE001
        if strict:
            raise RuntimeError(
                f"[업로드 거부] 확인 실패 — 유튜브 채널 조회에 실패했습니다(channel={channel}): {e}. "
                "어느 채널로 올라갈지 확인할 수 없어 중단합니다. 잠시 후 다시 시도하세요."
            ) from e
        logger.warning("[music-youtube] 채널 확인 실패(업로드는 계속): %s", e)
        return
    if not items:
        if strict:
            raise RuntimeError(
                f"[업로드 거부] 토큰 미연결 — 인증 토큰에 연결된 채널이 없습니다"
                f"(channel={channel}). /music/settings 에서 이 채널을 다시 연결하세요."
            )
        logger.warning("[music-youtube] 인증 토큰에 연결된 채널이 없습니다.")
        return
    actual_id = items[0].get("id", "")
    actual_title = items[0].get("snippet", {}).get("title", "")
    logger.warning(
        "[music-youtube] 인증 채널: id=%s title=%s (목표=%s, channel=%s)",
        actual_id, actual_title, target or "(미설정)", channel or "(기본)",
    )
    if target and actual_id != target:
        _key = _mo.channel_id_env_key(channel) if strict else "YOUTUBE_CHANNEL_ID_MUSIC"
        raise RuntimeError(
            f"[업로드 거부] 채널 불일치: 토큰 채널={actual_id}({actual_title}) ≠ "
            f"{_key}={target}. /music/settings 에서 재인증할 때 올바른 채널을 선택하세요."
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
    synthetic_media: bool | None = None,
    channel: str | None = None,
) -> dict:
    """음악 영상(mp4)을 음악 채널(Revezen)에 업로드. Returns {video_id, video_url}.

    백곰 upload_video 와 분리: 음악 OAuth(music_youtube_oauth.get_credentials),
    카테고리 10(음악). privacy 기본 'private'(검토 큐), 대시보드 공개 시 'public'.
    thumbnail_path 가 있으면 썸네일도 첨부. mp4_path 는 R2 URL/로컬 경로 모두 가능.
    title/description/tags 를 주면(#37 풍부화 메타) 그것을 쓰고, 없으면 build_music_metadata.
    업로드 성공 시 music_uploads 에 기록(실패해도 업로드는 성공).

    channel: 채널 축(운동 채널 3단계). 지정하면 그 채널의 토큰·채널ID 로 업로드하고
    검증을 엄격 모드로 돌린다(확인 불가 시 거부). None 이면 where 기존 동작.

    synthetic_media: AI 표시(status.containsSyntheticMedia). 우선순위는 백곰 upload_video 와
    동일하게 전달 인자(대시보드 토글) > env(YOUTUBE_SYNTHETIC_MEDIA) > False.
    이전에는 이 함수에 인자도 env 폴백도 없어 음악 영상에는 AI 표시가 **한 번도** 전달되지
    않았다(유튜브 스튜디오 AI use 미선택). 백곰 경로에만 구현돼 있던 것을 여기에도 맞춘다.
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

        creds = music_get_credentials(channel)
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        _verify_music_channel(youtube, channel)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "tags": tags,
                "categoryId": "10",        # 음악
                "defaultLanguage": "ko",
                "defaultAudioLanguage": "ko",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        # AI 표시 — 인자(대시보드 토글) > env > False. 값의 출처도 함께 로그로 남긴다.
        if synthetic_media is None:
            _raw_env = (os.getenv("YOUTUBE_SYNTHETIC_MEDIA") or "").strip().lower()
            synthetic = _raw_env in ("1", "true", "on", "yes")
            _src = f"env(YOUTUBE_SYNTHETIC_MEDIA={_raw_env or '미설정'})" if _raw_env else "기본값(False)"
        else:
            synthetic = bool(synthetic_media)
            _src = "대시보드 토글"
        if synthetic:
            body["status"]["containsSyntheticMedia"] = True
        logger.warning(
            "[youtube-debug] containsSyntheticMedia=%s (출처: %s)", synthetic, _src
        )
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
def _music_youtube_client(channel: str | None = None):
    """음악 채널 YouTube 클라이언트(force-ssl 포함 스코프 필요). channel 미지정 → where."""
    from googleapiclient.discovery import build
    from services.music_youtube_oauth import get_credentials as music_get_credentials
    creds = music_get_credentials(channel)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload_captions(video_id: str, srt_by_lang: dict[str, str], *, channel: str | None = None) -> dict:
    """언어별 SRT 를 자막 트랙으로 업로드(captions.insert). {uploaded:[lang...], failed:{lang:err}}.

    force-ssl 스코프 필요(재인증). 실패는 언어별로 격리(한 언어 실패가 나머지 막지 않음).
    """
    import tempfile
    from pathlib import Path
    from googleapiclient.http import MediaFileUpload

    uploaded: list[str] = []
    failed: dict[str, str] = {}
    skipped: list[str] = []  # SRT 자체가 비어 업로드 시도조차 안 한 언어(번역 누락 신호)
    if not srt_by_lang:
        logger.warning("[music-youtube] 자막 SRT 가 하나도 없음 — 업로드 생략")
        return {"uploaded": [], "failed": {}, "skipped": []}
    youtube = _music_youtube_client(channel)
    with tempfile.TemporaryDirectory(prefix="srt_") as tmp:
        for lang, srt in srt_by_lang.items():
            if not (srt or "").strip():
                skipped.append(lang)
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
    # 실패·건너뜀을 구분해 남긴다 — 조용히 사라지면 원인 추적이 불가능하다.
    if skipped:
        logger.warning(
            "[music-youtube] 자막 건너뜀(SRT 비어 있음) %d개: %s — 해당 언어 가사 번역 누락 의심",
            len(skipped), ",".join(sorted(skipped)),
        )
    if failed:
        logger.warning(
            "[music-youtube] 자막 업로드 실패 %d개: %s",
            len(failed), "; ".join(f"{k}({v[:80]})" for k, v in sorted(failed.items())),
        )
    logger.warning(
        "[music-youtube] 자막 %d개 업로드(실패 %d, 건너뜀 %d) 성공=%s",
        len(uploaded), len(failed), len(skipped), ",".join(sorted(uploaded)) or "-",
    )
    return {"uploaded": uploaded, "failed": failed, "skipped": skipped}


# 유튜브 description 상한은 5000자. 여유 100자를 두고 자른다.
_MAX_DESCRIPTION = 4900


def _clamp_description(desc: str, lng: str) -> str:
    """description 길이 가드. 초과분은 마지막 줄바꿈 기준으로 잘라 문장이 덜 끊기게 한다.

    30곡 롱폼을 태국어·힌디어로 번역하면 5000자를 넘길 수 있고, 넘기면 videos.update
    전체가 400 으로 떨어져 **전 언어가 날아간다**. 언어별로 미리 잘라 그 사고를 막는다.
    """
    if len(desc) <= _MAX_DESCRIPTION:
        return desc
    orig = len(desc)
    cut = desc[:_MAX_DESCRIPTION]
    nl = cut.rfind("\n")
    if nl > _MAX_DESCRIPTION // 2:  # 너무 앞에서 끊기면 줄바꿈 대신 문자 단위로
        cut = cut[:nl]
    cut = cut.rstrip()
    logger.warning("[music-youtube] %s description 길이 초과로 절단(%d자)", lng, orig)
    return cut


def set_localizations(
    video_id: str, localizations: dict[str, dict], default_lang: str = "ko",
    *, channel: str | None = None,
) -> dict:
    """제목·설명 다국어 적용(videos.update localizations). {ok, error, applied, failed}.

    localizations: {lang: {title, description}}. 기존 snippet 보존 + defaultLanguage 설정.

    한 언어라도 무효하면 videos.update 전체가 400 이 되어 **전 언어를 잃는다**. 그래서
    1차로 전체를 한 번에 시도하고(성공하면 API 1회로 끝), 실패하면 언어를 하나씩 누적
    적용해 **성공한 언어만이라도 살린다**(upload_captions 의 언어별 격리와 같은 취지).
    반환에 applied/failed 가 추가됐지만 기존 호출부가 보는 ok/error 키는 유지한다.
    """
    if not localizations:
        return {"ok": False, "error": "localizations 비어있음", "applied": [], "failed": {}}
    try:
        youtube = _music_youtube_client(channel)
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return {"ok": False, "error": "영상을 찾을 수 없음", "applied": [], "failed": {}}
        snippet = items[0]["snippet"]
        snippet["defaultLanguage"] = default_lang
        snippet["defaultAudioLanguage"] = default_lang
        loc = {
            lng: {
                "title": str(d.get("title", ""))[:100],
                "description": _clamp_description(str(d.get("description", "")), lng),
            }
            for lng, d in localizations.items()
            if isinstance(d, dict) and d.get("title")
        }
    except Exception as e:  # noqa: BLE001 - 준비 단계 실패(인증·조회)
        logger.warning("[music-youtube] localizations 준비 실패: %s", e)
        return {"ok": False, "error": str(e)[:200], "applied": [], "failed": {}}
    if not loc:
        return {"ok": False, "error": "적용할 언어 없음(title 빈 값)", "applied": [], "failed": {}}

    def _update(payload: dict) -> None:
        youtube.videos().update(
            part="snippet,localizations",
            body={"id": video_id, "snippet": snippet, "localizations": payload},
        ).execute()

    # 1차 — 전체 일괄(정상 경로, API 1회).
    try:
        _update(loc)
        logger.warning("[music-youtube] localizations %d개 언어 적용", len(loc))
        return {"ok": True, "error": None, "applied": sorted(loc), "failed": {}}
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[music-youtube] localizations 일괄 적용 실패 — 언어별 개별 적용으로 폴백: %s", e
        )

    # 2차 — 언어를 하나씩 누적 적용. 마지막으로 성공한 payload 가 영상의 최종 상태다.
    applied: dict[str, dict] = {}
    failed: dict[str, str] = {}
    for lng in sorted(loc):
        trial = dict(applied)
        trial[lng] = loc[lng]
        try:
            _update(trial)
            applied = trial
        except Exception as e:  # noqa: BLE001 - 언어별 격리
            failed[lng] = str(e)[:200]
            logger.warning("[music-youtube] localizations 적용 실패(%s): %s", lng, e)
    if applied:
        logger.warning(
            "[music-youtube] localizations 부분 적용: 성공 %d개(%s) / 실패 %d개(%s)",
            len(applied), ",".join(sorted(applied)),
            len(failed), ",".join(sorted(failed)) or "-",
        )
        return {"ok": True, "error": None, "applied": sorted(applied), "failed": failed}
    err = "; ".join(f"{k}: {v}" for k, v in list(failed.items())[:3])[:200] or "전 언어 실패"
    logger.warning("[music-youtube] localizations 전 언어 실패: %s", err)
    return {"ok": False, "error": err, "applied": [], "failed": failed}
