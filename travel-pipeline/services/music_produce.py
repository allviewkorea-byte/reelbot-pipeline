"""다곡 오케스트레이션 (Rooftop Music) — 주제 1개 → 완성 오디오.

흐름: music_lyrics(N개 가사, 헌법 3-스테이지) → 각 가사로 보컬 곡 생성
(music_suno, instrumental=false) → R2 저장 + 가사 원문 R2 보존 → music_master
마스터링 → music_mix 롱폼 믹스(가사 임베드) = 완성 오디오 + 오프셋 JSON.

부분 실패 허용(곡 하나 실패해도 나머지로 진행), 멱등(마스터/믹스가 head_object 로 스킵).
신규 버킷·테이블 없음 — 가사 원문은 music-masters/{slug}/lyrics/{audio_id}.txt.
"""

from __future__ import annotations

import logging
import os
import random
import re

from adapters import r2_storage
from services import music_genres, music_lyrics, music_master, music_mix, music_store, music_suno

logger = logging.getLogger(__name__)

_MIN_DURATION_SEC = float(os.getenv("MUSIC_MIN_DURATION_SEC", "150"))  # 재활용 풀 짧은 트랙 은퇴 기준

# 시티팝 기본 베이스 스타일(플랜이 곡별 변주를 주면 그쪽 우선).
DEFAULT_BASE_STYLE = "city pop, 80s Japanese citypop, warm analog, lush chords, nostalgic"

# 보컬 명료도 — 반주에 묻히지 않게 모든 보컬 곡 style 에 붙인다(#5.1).
_VOCAL_CLARITY = "clear, present, polished vocals"
_GENDERS = ("female", "male")
# style 문자열에 이미 박힌 성별 단어 제거용(곡별 랜덤 성별과 충돌 방지).
_GENDER_RE = re.compile(r"\b(?:fe)?male\b", re.IGNORECASE)


def _assign_genders(n: int) -> list[str]:
    """N곡에 줄 성별 리스트(곡 단위 랜덤). N≥2면 남·여 최소 1곡씩 보장(쏠림 방지),
    순서는 무작위. 시드 고정 안 함(매번 달라야 함)."""
    if n <= 0:
        return []
    if n == 1:
        return [random.choice(_GENDERS)]
    genders = ["female", "male"] + [random.choice(_GENDERS) for _ in range(n - 2)]
    random.shuffle(genders)
    return genders


def _vocal_style(base: str, gender: str) -> str:
    """곡 style 에 랜덤 성별 + 명료도 표현을 붙인다(기존 성별 단어는 제거 후)."""
    base = _GENDER_RE.sub("", base or "")
    base = re.sub(r"\s{2,}", " ", base).strip().strip(",").strip()
    return f"{base}, {gender} vocals, {_VOCAL_CLARITY}"



def _generate_with_retry(theme: dict, log, *, max_retries: int | None = None) -> dict:
    """generate_and_store 1회 호출. 결과를 그대로 반환(재생성 없음).

    길이 재시도는 Suno 크레딧 낭비(8곡 폭발)를 유발하므로 제거됨.
    max_retries 인자는 하위호환용으로 남겨두되 무시한다.
    """
    return music_suno.generate_and_store(theme)


# ── Suno 재활용(#46) ───────────────────────────────────────────────────
# 모델: Suno 1회 호출=2클립이지만 믹스엔 1클립만 쓴다(#34-B). 나머지 1클립은
# used=false 로 DB(music_tracks)에 쌓여 "재활용 풀"이 된다. 다음 같은 장르 제작 때
# 풀에서 1곡을 꺼내 쓰면 Suno 호출(과금)을 통째로 건너뛴다 → 크레딧 절반 절약.
# 안전: 재활용 검색·마킹은 전부 best-effort(실패/없음 → Suno 정상 호출 폴백).
# 범위: 연주(instrumental)만 재활용한다. 보컬은 곡마다 가사·자막 정합이 필요해
#       이번엔 항상 새로 생성(보컬 트랙도 genre/used 는 기록 → 향후 재활용 여지).


def _recycle_track(genre_id: str | None, seen: set[str], log) -> dict | None:
    """장르 풀에서 미사용 트랙 1개를 꺼내 used=true 마킹 후 rec 으로 반환(없으면 None).

    rec 은 신규 생성 클립과 같은 형태({audio_id, r2_key, duration, title, tags}). r2_key 는
    원본(다른 theme_slug) 경로 — master_track 이 r2_key 우선으로 소스를 읽으므로 그대로 동작.
    """
    if not genre_id:
        return None
    # 어떤 실패든(검색·마킹·예외) None 반환 → 호출부가 Suno 정상 호출(폴백). 절대 막지 않음.
    try:
        row = music_store.find_unused_track(genre_id, exclude_ids=seen)
        if not row:
            return None
        audio_id = row.get("audio_id") or row.get("id")
        r2_key = row.get("r2_key")
        if not audio_id or not r2_key:
            return None
        # 길이 가드 — 재시도로 걸러졌어야 할 짧은 트랙이 풀에 남아 무음처럼 재사용되는 것 방지.
        # 길이가 알려져 있고 미달이면 used=true 로 '은퇴'시키고 Suno 정상 호출로 폴백.
        rdur = row.get("duration")
        try:
            if rdur is not None and 0 < float(rdur) < _MIN_DURATION_SEC:
                seen.add(audio_id)
                music_store.mark_track_used(audio_id)
                logger.warning(
                    "[produce] 재활용 풀 짧은 트랙 은퇴 %.0f초 (id=%s) — Suno 폴백",
                    float(rdur), audio_id,
                )
                return None
        except (TypeError, ValueError):
            pass
        seen.add(audio_id)
        if not music_store.mark_track_used(audio_id):
            # 마킹 실패해도 진행(다음에 중복 사용될 수 있으나 렌더 실패보단 낫다).
            logger.warning("[produce] 재활용 used 마킹 실패(id=%s) — 진행", audio_id)
        log(f"재활용 — Suno 호출 생략 (audio_id={audio_id})")
        return {
            "audio_id": audio_id,
            "r2_key": r2_key,
            "duration": row.get("duration"),
            "title": row.get("title") or "",
            "tags": row.get("tags") or "",
        }
    except Exception as e:  # noqa: BLE001 - 재활용 실패는 절대 제작을 막지 않는다
        logger.warning("[produce] 재활용 시도 실패(genre=%s) — Suno 폴백: %s", genre_id, e)
        return None


def _consume_generated(all_clips: list[dict], seen: set[str]) -> list[dict]:
    """신규 생성 클립 처리: 첫 클립만 사용(나머지는 재활용 풀로 적립), 사용분 used=true 마킹.

    이번 런에서 본 audio_id 는 전부 seen 에 넣어(막 적립한 둘째 클립 포함) 같은 런 내
    중복 사용을 막는다(둘째 클립은 DB 에선 used=false 로 남아 다음 런에서 재활용 가능).
    """
    for c in all_clips:
        aid = c.get("audio_id")
        if aid:
            seen.add(aid)
    used = all_clips[:1]
    for c in used:
        aid = c.get("audio_id")
        if aid and not music_store.mark_track_used(aid):
            logger.warning("[produce] 사용분 used 마킹 실패(id=%s) — 진행", aid)
    return used


def _gen_vocal(
    theme_slug: str, songs: list[dict], base_style: str, genre_theme: str, log,
    *, genre_id: str | None = None, seen: set[str] | None = None,
    is_tag_path: bool = False, action: str = "",
) -> tuple[list[dict], dict[str, str]]:
    """보컬 경로: 곡별 가사로 보컬곡 생성(부분 실패 허용) + 가사 원문 R2 보존.

    곡마다 남/여 보컬을 랜덤 주입(N≥2면 남·여 모두 포함)하고 명료도 표현을 style 에
    붙여, 한 믹스 안에서도 영상끼리도 성별이 예측 불가하게 한다(#5.1).
    """
    produced: list[dict] = []
    lyrics_by_id: dict[str, str] = {}
    # 가사 있는 곡만 추려 성별을 균형 배정(쏠림 방지).
    valid = [s for s in songs if (s.get("lyrics") or "").strip()]
    if len(valid) < len(songs):
        logger.warning("[produce] 가사 빈 곡 %d개 건너뜀", len(songs) - len(valid))
    genders = _assign_genders(len(valid))
    seen = seen if seen is not None else set()
    for i, (s, gender) in enumerate(zip(valid, genders), 1):
        lyric = s["lyrics"].strip()
        theme = {
            "theme_slug": theme_slug,
            "instrumental": False,
            "style": _vocal_style(s.get("style") or base_style, gender),
            "title": s.get("title") or "",  # #52-A 빈값 → Suno 가 곡 제목 자동 생성(장르명+번호 표시 방지)
            "lyrics": lyric,
            "vocalGender": gender,
            "genre_id": genre_id,  # #46: 트랙에 장르 기록(used=false로 적립)
            "action": action,
        }
        try:
            log(f"보컬 생성 {i}/{len(valid)} [{gender}]: {s.get('title')}")
            res = _generate_with_retry(theme, log, max_retries=1 if is_tag_path else None)
        except Exception as e:  # noqa: BLE001 - 1곡 실패가 전체를 막지 않게
            logger.warning("[produce] 곡 %d 보컬 생성 실패: %s", i, e)
            continue
        # suno 1회 호출 = 2클립(같은 가사/스타일 변주). 곡수 N = N곡이 되도록 첫 클립만
        # 사용하고 둘째 클립은 used=false 로 적립(#34-B / #46). 보컬은 재활용하지 않음.
        all_clips = _consume_generated(res.get("tracks", []), seen)
        for rec in all_clips:
            audio_id = rec.get("audio_id")
            if not audio_id:
                continue
            lyrics_by_id[audio_id] = lyric
            # 가사 원문 R2 보존(#4 자막용). 실패해도 파이프라인은 계속.
            try:
                if r2_storage.is_available():
                    r2_storage.upload_lyrics_text(lyric, theme_slug, audio_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("[produce] 가사 원문 R2 저장 실패(audio_id=%s): %s", audio_id, e)
            produced.append({
                **rec,
                "sub_theme": s.get("sub_theme", ""),
                "core_message": s.get("core_message", ""),
                "lyrics": lyric,
            })
    return produced, lyrics_by_id


def _gen_instrumental(
    theme_slug: str, n: int, style: str, genre_theme: str, log,
    *, genre_id: str | None = None, seen: set[str] | None = None,
    is_tag_path: bool = False, action: str = "",
    theme_dict: dict | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """연주 경로: 가사 없이 style 만으로 연주곡 N회 생성(instrumental=True, 부분 실패 허용).

    가사 없음 → lyrics_by_id 는 빈 dict(믹스 JSON 에 가사 미포함).
    #46: 곡마다 먼저 장르 재활용 풀을 확인 — 미사용 트랙이 있으면 Suno 호출 없이 재활용.
    is_tag_path: 태그 조합 경로면 True — 길이 힌트 보강 + 재시도 1회 제한(비용 절약).
    theme_dict: 원본 theme(제목 생성용). 없으면 빈 dict.
    """
    produced: list[dict] = []
    seen = seen if seen is not None else set()
    # 태그 경로: 가사 없는 연주곡은 길이 힌트가 유일한 장치 → _with_length_hint 로 보강.
    effective_style = music_lyrics._with_length_hint(style) if is_tag_path else style
    tag_retries = 1 if is_tag_path else None  # 태그 경로 재시도 1회, 14장르는 기본(2회)

    # 곡별 다양한 제목 + 스타일 변주 생성(LLM). 실패 시 빈 리스트 → 공통 style/Suno 자동 제목 폴백.
    variations: list[dict] = []
    try:
        from services import music_meta
        td = dict(theme_dict or {})
        td.setdefault("genre_theme", genre_theme)
        variations = music_meta.generate_instrumental_variations(n, effective_style, td)
        if variations:
            log(f"연주곡 제목+변주 {len(variations)}개 생성")
    except Exception as e:  # noqa: BLE001
        logger.warning("[produce] 연주곡 변주 생성 실패(공통 style 폴백): %s", e)

    for i in range(1, n + 1):
        var = variations[i - 1] if i <= len(variations) else {}
        title = var.get("title", "")
        var_style = var.get("style", "")
        # 변주 style이 있으면 사용, 없으면 공통 effective_style 폴백.
        track_style = var_style if var_style else effective_style
        # 태그 경로 길이 힌트: 변주 style에도 적용.
        if is_tag_path and var_style:
            track_style = music_lyrics._with_length_hint(track_style)

        # ① 재활용 우선 — 같은 장르 미사용 트랙이 있으면 Suno 건너뜀(크레딧 0).
        recycled = _recycle_track(genre_id, seen, log)
        if recycled is not None:
            if title:
                recycled["title"] = title
            produced.append({**recycled})
            continue
        # ② 없으면 Suno 정상 호출(폴백).
        theme = {
            "theme_slug": theme_slug,
            "instrumental": True,
            "style": track_style,
            "title": title,
            "genre_id": genre_id,  # #46: 둘째 클립이 used=false 로 적립 → 다음에 재활용
            "action": action,
        }
        try:
            log(f"연주 생성 {i}/{n}: {title or '(자동)'}")
            res = _generate_with_retry(theme, log, max_retries=tag_retries)
        except Exception as e:  # noqa: BLE001 - 1곡 실패가 전체를 막지 않게
            logger.warning("[produce] 연주 %d 생성 실패: %s", i, e)
            continue
        # suno 1회 호출 = 2클립. 첫 클립만 사용(used=true), 둘째는 적립(used=false, #46).
        for rec in _consume_generated(res.get("tracks", []), seen):
            if rec.get("audio_id"):
                if title and not (rec.get("title") or "").strip():
                    rec["title"] = title
                produced.append({**rec})
    return produced, {}


def produce(
    theme_slug: str,
    *,
    n: int = 3,
    genre_theme: str = "city pop",
    base_style: str = DEFAULT_BASE_STYLE,
    language: str = "ko",
    minutes: float = 10.0,
    sub_theme_pool: list[str] | None = None,
    lyrics: list[dict] | None = None,
    track_type: str = "vocal",
    style_prompt: str | None = None,
    lyric_tone: str | None = None,
    do_master: bool = True,
    do_mix: bool = True,
    seed: int | None = None,
    model: str | None = None,
    genre_id: str | None = None,
    action: str = "",
    progress=None,
) -> dict:
    """주제 → N곡 생성 → 마스터 → 믹스. 완성 오디오 메타 반환.

    track_type 으로 분기:
      - "instrumental": 가사 스킵, style_prompt(없으면 base_style)로 연주곡 N회 생성.
      - "vocal"(기본): 헌법 3-스테이지 가사 → 보컬곡. lyric_tone 이 있으면 작성에 반영.
    lyrics(선택, vocal): 이미 만든/검수한 가사 리스트를 주면 가사 생성을 건너뛴다.
    genre_id(#46): 14장르 id. 있으면 (1) 고정 Suno 태그·instrumental 적용(태그 매핑),
      (2) 같은 장르 미사용 트랙 재활용. 없거나 태그 없는 장르 → 기존 LLM 스타일 폴백.
    action: 어떨때 id(예: sleep, study). 트랙 DB에 저장(라이브러리 필터용).
    Returns: {theme_slug, track_type, songs:[...], produced:[record...], mastered, mix}
    """

    def _log(msg: str) -> None:
        logger.info("[produce] %s", msg)
        if progress:
            progress(msg)

    # 장르 고정 태그 매핑(#46-D) — 있으면 style/instrumental 을 장르 설정으로 덮어쓴다.
    cfg = music_genres.suno_config(genre_id)
    if cfg:
        is_instrumental = cfg["instrumental"]
        base_style = cfg["style"]
        style_prompt = cfg["style"]
        _log(f"장르 고정 태그 적용: {genre_id} ({'연주' if is_instrumental else '보컬'})")
    else:
        is_instrumental = (track_type or "vocal").strip().lower() == "instrumental"

    seen: set[str] = set()  # #46: 이번 런에서 사용/적립한 audio_id(같은 런 중복 재활용 방지)

    if is_instrumental:
        # ① 가사 스킵. style_prompt 우선(주제/고정태그), 없으면 base_style.
        songs = []
        _log(f"연주 경로 — 가사 스킵, {n}곡 생성")
        produced, lyrics_by_id = _gen_instrumental(
            theme_slug, n, style_prompt or base_style, genre_theme, _log,
            genre_id=genre_id, seen=seen,
            is_tag_path=not cfg, action=action,
            theme_dict={"slug": theme_slug, "genre": genre_theme,
                        "genre_theme": genre_theme, "action": action},
        )
    else:
        # ① 가사(헌법 3-스테이지) — 주어지면 재사용(검수본), lyric_tone 반영.
        songs = lyrics if lyrics is not None else music_lyrics.generate_lyrics(
            genre_theme, n, sub_theme_pool=sub_theme_pool, language=language,
            model=model, tone=lyric_tone, genre_id=genre_id,
        )
        # 고정 태그 보컬 장르: 곡별 style 을 고정 태그로 통일(일관성). 없으면 기존대로.
        if cfg:
            for s in songs:
                s["style"] = cfg["style"]
        _log(f"가사 {len(songs)}곡 확보")
        # ② 곡별 보컬 생성.
        produced, lyrics_by_id = _gen_vocal(
            theme_slug, songs, base_style, genre_theme, _log,
            genre_id=genre_id, seen=seen,
            is_tag_path=not cfg, action=action,
        )

    if not produced:
        raise RuntimeError("생성 결과가 없습니다(전 곡 실패).")
    _log(f"트랙 {len(produced)}개 생성")

    # ③ 마스터링(이번 배치만, 멱등) — 연주/보컬 공통.
    mastered = []
    if do_master:
        _log("마스터링(2-pass loudnorm -14 LUFS)...")
        mastered = music_master.master_theme(theme_slug, produced)

    # ④ 롱폼 믹스 — 연주는 lyrics_by_id 없이, 보컬은 가사 임베드.
    mix = None
    if do_mix:
        _log(f"믹스(목표 {minutes}분)...")
        mix = music_mix.build_mix(
            theme_slug, produced, minutes=minutes, seed=seed,
            lyrics_by_id=lyrics_by_id or None,
        )

    return {
        "theme_slug": theme_slug,
        "track_type": "instrumental" if is_instrumental else "vocal",
        "songs": songs,
        "produced": produced,
        "mastered": mastered,
        "mix": mix,
    }


def run_theme(
    *,
    theme: dict | None = None,
    n: int | None = None,
    minutes: float = 10.0,
    seed: int | None = None,
    do_master: bool = True,
    do_mix: bool = True,
    avoid_recent: int = 10,
    persist: bool = True,
    theme_model: str | None = None,
    lyrics_model: str | None = None,
    video: bool = False,
    video_seconds: float | None = None,
    upload: bool = False,
    progress=None,
) -> dict:
    """주제 1개 → 음원 믹스 1개(얇은 오케스트레이터).

    theme 미지정 시 music_theme.generate_theme() 로 1개 생성한다. 주제의 type 으로
    produce 가 연주/보컬 경로를 자동 선택한다.
    video=True 면 믹스 후 영상(mp4)까지 이어 만든다(기본 False — 기존 동작 회귀 0).
    Returns: {theme, mix, result, video?}.
    """
    from services import music_theme  # 지연 import(순환 회피)

    if theme is None:
        theme = music_theme.generate_theme(
            avoid_recent=avoid_recent, persist=persist, model=theme_model
        )
    slug = theme.get("slug") or theme.get("theme_slug")
    if not slug:
        raise ValueError("theme 에 slug 가 없습니다.")
    count = n or int(theme.get("track_count") or 3)

    # #46: 주제의 genre id 우선, 없으면 텍스트로 14장르 분류(best-effort). None → LLM 폴백.
    genre_id = theme.get("genre_id") or music_genres.classify_theme(theme)

    result = produce(
        slug,
        n=count,
        genre_theme=theme.get("genre") or "music",
        base_style=theme.get("style_prompt") or DEFAULT_BASE_STYLE,
        style_prompt=theme.get("style_prompt"),
        track_type=theme.get("type") or "vocal",
        lyric_tone=theme.get("lyric_tone"),
        minutes=minutes,
        seed=seed,
        do_master=do_master,
        do_mix=do_mix,
        model=lyrics_model,
        genre_id=genre_id,
        action=(theme.get("tag_combo") or {}).get("action") or "",
        progress=progress,
    )
    out = {"theme": theme, "mix": result.get("mix"), "result": result}

    # (선택) 영상화 — 믹스가 있을 때만. 실패해도 음원 결과는 보존.
    if video and result.get("mix"):
        from services import music_video  # 지연 import(선택 기능)
        if progress:
            progress("영상 합성...")
        out["video"] = music_video.make_video(
            theme, result["mix"], seconds=video_seconds
        )

    # (선택) 음악 채널 유튜브 비공개 업로드 — 영상이 있을 때만.
    if upload and out.get("video"):
        from services.youtube_upload import upload_music_video  # 지연 import
        if progress:
            progress("유튜브 업로드(비공개)...")
        out["upload"] = upload_music_video(
            out["video"]["video_url"], theme, result["mix"]
        )
    return out
