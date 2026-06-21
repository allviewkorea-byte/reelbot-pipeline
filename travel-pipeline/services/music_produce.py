"""다곡 오케스트레이션 (Rooftop Music) — 주제 1개 → 완성 오디오.

흐름: music_lyrics(N개 가사, 헌법 3-스테이지) → 각 가사로 보컬 곡 생성
(music_suno, instrumental=false) → R2 저장 + 가사 원문 R2 보존 → music_master
마스터링 → music_mix 롱폼 믹스(가사 임베드) = 완성 오디오 + 오프셋 JSON.

부분 실패 허용(곡 하나 실패해도 나머지로 진행), 멱등(마스터/믹스가 head_object 로 스킵).
신규 버킷·테이블 없음 — 가사 원문은 music-masters/{slug}/lyrics/{audio_id}.txt.
"""

from __future__ import annotations

import logging

from adapters import r2_storage
from services import music_lyrics, music_master, music_mix, music_suno

logger = logging.getLogger(__name__)

# 시티팝 기본 베이스 스타일(플랜이 곡별 변주를 주면 그쪽 우선).
DEFAULT_BASE_STYLE = "city pop, 80s Japanese citypop, warm analog, lush chords, nostalgic"


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
    do_master: bool = True,
    do_mix: bool = True,
    seed: int | None = None,
    model: str | None = None,
    progress=None,
) -> dict:
    """주제 → N곡 가사 → 보컬 생성 → 마스터 → 믹스. 완성 오디오 메타 반환.

    lyrics(선택): 이미 만든/검수한 가사 리스트를 주면 가사 생성을 건너뛴다.
    Returns: {theme_slug, songs:[...], produced:[record...], mastered, mix}
    """

    def _log(msg: str) -> None:
        logger.info("[produce] %s", msg)
        if progress:
            progress(msg)

    # ① 가사 (헌법 3-스테이지) — 주어지면 재사용(검수본).
    songs = lyrics if lyrics is not None else music_lyrics.generate_lyrics(
        genre_theme, n, sub_theme_pool=sub_theme_pool, language=language, model=model
    )
    _log(f"가사 {len(songs)}곡 확보")

    # ② 곡별 보컬 생성(부분 실패 허용) + 가사 원문 R2 보존.
    produced: list[dict] = []
    lyrics_by_id: dict[str, str] = {}
    for i, s in enumerate(songs, 1):
        lyric = (s.get("lyrics") or "").strip()
        if not lyric:
            logger.warning("[produce] 곡 %d 가사 비어 있음 — 건너뜀", i)
            continue
        theme = {
            "theme_slug": theme_slug,
            "instrumental": False,
            "style": s.get("style") or base_style,
            "title": s.get("title") or f"{genre_theme} {i}",
            "lyrics": lyric,
        }
        if s.get("vocalGender"):
            theme["vocalGender"] = s["vocalGender"]
        try:
            _log(f"보컬 생성 {i}/{len(songs)}: {s.get('title')}")
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

    if not produced:
        raise RuntimeError("보컬 생성 결과가 없습니다(전 곡 실패).")
    _log(f"보컬 트랙 {len(produced)}개 생성")

    # ③ 마스터링(이번 배치만, 멱등).
    mastered = []
    if do_master:
        _log("마스터링(2-pass loudnorm -14 LUFS)...")
        mastered = music_master.master_theme(theme_slug, produced)

    # ④ 롱폼 믹스(가사 임베드).
    mix = None
    if do_mix:
        _log(f"믹스(목표 {minutes}분)...")
        mix = music_mix.build_mix(
            theme_slug, produced, minutes=minutes, seed=seed, lyrics_by_id=lyrics_by_id
        )

    return {
        "theme_slug": theme_slug,
        "songs": songs,
        "produced": produced,
        "mastered": mastered,
        "mix": mix,
    }
