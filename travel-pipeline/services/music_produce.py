"""다곡 오케스트레이션 (Rooftop Music) — 주제 1개 → 완성 오디오.

흐름: music_lyrics(N개 가사, 헌법 3-스테이지) → 각 가사로 보컬 곡 생성
(music_suno, instrumental=false) → R2 저장 + 가사 원문 R2 보존 → music_master
마스터링 → music_mix 롱폼 믹스(가사 임베드) = 완성 오디오 + 오프셋 JSON.

부분 실패 허용(곡 하나 실패해도 나머지로 진행), 멱등(마스터/믹스가 head_object 로 스킵).
신규 버킷·테이블 없음 — 가사 원문은 music-masters/{slug}/lyrics/{audio_id}.txt.
"""

from __future__ import annotations

import logging
import random
import re

from adapters import r2_storage
from services import music_lyrics, music_master, music_mix, music_suno

logger = logging.getLogger(__name__)

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


def _gen_vocal(
    theme_slug: str, songs: list[dict], base_style: str, genre_theme: str, log
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
    for i, (s, gender) in enumerate(zip(valid, genders), 1):
        lyric = s["lyrics"].strip()
        theme = {
            "theme_slug": theme_slug,
            "instrumental": False,
            "style": _vocal_style(s.get("style") or base_style, gender),
            "title": s.get("title") or f"{genre_theme} {i}",
            "lyrics": lyric,
            "vocalGender": gender,
        }
        try:
            log(f"보컬 생성 {i}/{len(valid)} [{gender}]: {s.get('title')}")
            res = music_suno.generate_and_store(theme)
        except Exception as e:  # noqa: BLE001 - 1곡 실패가 전체를 막지 않게
            logger.warning("[produce] 곡 %d 보컬 생성 실패: %s", i, e)
            continue
        for rec in res.get("tracks", []):
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
    theme_slug: str, n: int, style: str, genre_theme: str, log
) -> tuple[list[dict], dict[str, str]]:
    """연주 경로: 가사 없이 style 만으로 연주곡 N회 생성(instrumental=True, 부분 실패 허용).

    가사 없음 → lyrics_by_id 는 빈 dict(믹스 JSON 에 가사 미포함).
    """
    produced: list[dict] = []
    for i in range(1, n + 1):
        theme = {
            "theme_slug": theme_slug,
            "instrumental": True,
            "style": style,
            "title": f"{genre_theme} {i}",
        }
        try:
            log(f"연주 생성 {i}/{n}")
            res = music_suno.generate_and_store(theme)
        except Exception as e:  # noqa: BLE001 - 1곡 실패가 전체를 막지 않게
            logger.warning("[produce] 연주 %d 생성 실패: %s", i, e)
            continue
        for rec in res.get("tracks", []):
            if rec.get("audio_id"):
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
    progress=None,
) -> dict:
    """주제 → N곡 생성 → 마스터 → 믹스. 완성 오디오 메타 반환.

    track_type 으로 분기:
      - "instrumental": 가사 스킵, style_prompt(없으면 base_style)로 연주곡 N회 생성.
      - "vocal"(기본): 헌법 3-스테이지 가사 → 보컬곡. lyric_tone 이 있으면 작성에 반영.
    lyrics(선택, vocal): 이미 만든/검수한 가사 리스트를 주면 가사 생성을 건너뛴다.
    Returns: {theme_slug, track_type, songs:[...], produced:[record...], mastered, mix}
    """

    def _log(msg: str) -> None:
        logger.info("[produce] %s", msg)
        if progress:
            progress(msg)

    is_instrumental = (track_type or "vocal").strip().lower() == "instrumental"

    if is_instrumental:
        # ① 가사 스킵. style_prompt 우선(주제), 없으면 base_style.
        songs: list[dict] = []
        _log(f"연주 경로 — 가사 스킵, {n}곡 생성")
        produced, lyrics_by_id = _gen_instrumental(
            theme_slug, n, style_prompt or base_style, genre_theme, _log
        )
    else:
        # ① 가사(헌법 3-스테이지) — 주어지면 재사용(검수본), lyric_tone 반영.
        songs = lyrics if lyrics is not None else music_lyrics.generate_lyrics(
            genre_theme, n, sub_theme_pool=sub_theme_pool, language=language,
            model=model, tone=lyric_tone,
        )
        _log(f"가사 {len(songs)}곡 확보")
        # ② 곡별 보컬 생성.
        produced, lyrics_by_id = _gen_vocal(theme_slug, songs, base_style, genre_theme, _log)

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
    return out
