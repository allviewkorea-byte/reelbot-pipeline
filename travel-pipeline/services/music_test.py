"""테스트 영상(#19) — 즉석 10초 Remotion 렌더(유튜브 X, 검토 큐 저장 X).

대시보드 '테스트 영상 생성' 버튼용. make_video 를 거치지 않아(=record_pending·
youtube 미경유) DB·유튜브에 전혀 영향이 없다. 임시 주제 + 합성 오디오(둥근 바가
움직이도록) + 더미 배경으로 영상만 만들어 R2 임시 경로(music-videos/test/{uuid}.mp4)에
올리고 URL 을 돌려준다. Remotion(USE_REMOTION) 우선, 실패 시 ffmpeg 폴백(#18 동일).
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from adapters import r2_storage
from services import music_genres, music_video

logger = logging.getLogger(__name__)

# mood(장르) 키 → 테스트 주제. 14장르 프리셋은 music_genres SSOT(#45)에서 가져온다.
_DEFAULT_MOOD = music_genres.DEFAULT_GENRE


def _test_preset(key: str) -> dict:
    """장르 프리셋 → 테스트용(제목에 '테스트 ·' 접두) 사본."""
    base = music_genres.preset(key)
    p = dict(base)
    p["title_kr"] = f"테스트 · {base['title_kr']}"
    return p


def available_moods() -> list[str]:
    return list(music_genres.GENRE_IDS)


def _synth_audio(work: Path, seconds: float) -> Path:
    """이퀄 전 대역(저~고역)이 골고루 움직이도록 만든 합성 mp3.

    이전 버전은 196/330/523Hz 저주파만 있어 좌측 막대 ~10개만 반응했다(나머지 0).
    Remotion visualizeAudio 는 512샘플 FFT로 86Hz~10kHz 를 선형 매핑하므로, 전 대역을
    채우려면 광대역 소스가 필요하다. 화이트 노이즈(전 빈 평탄)로 모든 막대를 채우고,
    저역·고역 스윕 사인 2개로 '춤추는' 움직임을 준 뒤 트레몰로로 펄스를 얹는다.
    """
    out = work / "audio.mp3"
    d = f"{seconds}"
    # 코드(앵커) + 저역 스윕(150~1450Hz) + 고역 스윕(2200~7400Hz).
    expr = (
        "0.05*(sin(2*PI*220*t)+sin(2*PI*880*t)+sin(2*PI*3520*t))"
        "+0.08*sin(2*PI*(150+1300*(0.5+0.5*sin(2*PI*0.35*t)))*t)"
        "+0.07*sin(2*PI*(2200+5200*(0.5+0.5*sin(2*PI*0.22*t)))*t)"
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={d}",
            "-f", "lavfi", "-i", f"anoisesrc=d={d}:c=white:r=44100:a=0.05",
            "-filter_complex",
            "[1:a]highpass=f=80,lowpass=f=12000[n];"
            "[0:a][n]amix=inputs=2:duration=first:weights=0.7 1.0,"
            "tremolo=f=5:d=0.45,aformat=channel_layouts=stereo[a]",
            "-map", "[a]",
            "-c:a", "libmp3lame", "-q:a", "5",
            str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    return out


def _dummy_bg(work: Path) -> Path:
    """더미 배경(짙은 네이비 단색 1920x1080). 실제 썸네일/PLAY LIST 는 운영 영상에서."""
    out = work / "bg.png"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0x12203a:s=1920x1080:d=1",
            "-frames:v", "1", str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    return out


def _real_bg(work: Path, slug: str) -> Path | None:
    """운영 영상 배경(music_uploads.thumbnail_r2_key)을 R2 에서 받아 bg 로 사용.

    같은 slug 우선, 없으면 최근 업로드/검토대기 중 thumbnail_r2_key 보유분 1개.
    조회·다운로드 실패 시 None → 호출부가 더미 배경으로 폴백.
    """
    try:
        from services import music_uploads
        rows = music_uploads.list_uploaded(limit=20) + music_uploads.list_pending()
        cand: str | None = None
        for row in rows:
            if str(row.get("slug") or "").startswith("test_"):
                continue  # 테스트 카드(첫프레임=텍스트 포함)는 배경으로 쓰지 않음
            tk = (row.get("thumbnail_r2_key") or "").strip()
            if not tk:
                continue
            if row.get("slug") == slug:  # slug 일치 우선
                cand = tk
                break
            if cand is None:  # 폴백: 가장 최근 보유분
                cand = tk
        if not cand:
            return None
        dest = work / "bg.png"
        r2_storage.download_music_object(cand, str(dest))
        logger.info("[music-test] 실제 배경 사용(key=%s)", cand)
        return dest
    except Exception as e:  # noqa: BLE001 - 실패 시 더미 배경 폴백
        logger.warning("[music-test] 실제 배경 로드 실패(더미 폴백): %s", e)
        return None


def render_test(mood: str | None = None, *, seconds: float = 10.0) -> dict:
    """임시 주제로 10초 영상 렌더 → R2 임시 업로드 → {video_url, engine, ...}.

    Remotion(USE_REMOTION on) 우선, 실패/off 면 ffmpeg 폴백. 유튜브·큐 미경유.
    """
    music_video._require_ffmpeg()
    key = music_genres.normalize_mood_key(mood or _DEFAULT_MOOD)
    preset = _test_preset(key)

    # 단일 곡(전체 길이) — 제목 타이핑이 한 번만 진행되게(곡 전환 재타이핑 회피).
    tracks = [{"title": preset["tracks"][0], "start_sec": 0.0}]
    mood_hint = " ".join(
        str(preset.get(k, "")) for k in ("mood", "genre", "situation")
    ).strip()
    # #20: 테스트도 인트로·텍스트·색감을 보여주도록 viz_spec 동봉(결정적 fallback, GPT 미사용).
    theme = {
        "slug": key, "title_kr": preset["title_kr"], "genre": preset["genre"],
        "mood": preset["mood"], "situation": preset["situation"],
    }
    from services import music_viz_analyzer
    viz_spec = music_viz_analyzer.analyze_song(theme, None, use_gpt=False)

    work = Path(tempfile.mkdtemp(prefix="mtest_"))
    try:
        audio = _synth_audio(work, seconds)
        bg = _real_bg(work, key) or _dummy_bg(work)  # 운영 썸네일 배경 우선, 없으면 더미
        out = work / "test.mp4"

        engine = "ffmpeg"
        rendered = False
        # 채널 디자인 본부 설정(where;____·이퀄·폰트 등)을 테스트에도 반영. 미설정/오류 시 None → 현재값 폴백.
        design_config = None
        try:
            from services import music_channel
            design_config = music_channel.get_design_config()
        except Exception as e:  # noqa: BLE001 - 조회 실패 시 기본값으로 진행
            logger.warning("[music-test] design_config 조회 실패(기본값 진행): %s", e)
        if music_video.remotion_enabled():
            try:
                music_video._render_remotion(
                    str(bg), str(audio), str(out),
                    tracks=tracks, mood=mood_hint, duration=seconds, viz_spec=viz_spec,
                    design_config=design_config,
                )
                rendered = True
                engine = "remotion"
            except Exception as e:  # noqa: BLE001 - Remotion 실패 시 ffmpeg 폴백
                logger.warning("[music-test] Remotion 실패 → ffmpeg 폴백: %s", e)
        if not rendered:
            music_video.compose_video(
                str(bg), str(audio), str(out),
                tracks=tracks, title_kr=preset["title_kr"], duration=seconds,
                static_bg=True,
            )

        if not r2_storage.is_available():
            raise RuntimeError("R2 미설정 — 테스트 영상 업로드 불가")
        vid = uuid.uuid4().hex
        slug = f"test_{int(time.time())}"
        name = f"{vid}.mp4"
        video_url = r2_storage.upload_music_video(str(out), "test", name, content_type="video/mp4")

        # 배경(깨끗한 bg) → 검토 카드 썸네일 + 재렌더 배경(첫프레임=텍스트 박힘 회피).
        # ⚠️ 큐 API 는 thumbnail_url 을 music_thumbnail_url(slug, mix_id) 로 '재구성'하므로
        #    반드시 표준 썸네일 경로(music-thumbnails/{slug}/{mix_id}.png)에 올려야 미리보기가 뜬다.
        thumb_key: str | None = None
        try:
            r2_storage.upload_music_thumbnail(str(bg), slug, vid)
            thumb_key = r2_storage.music_thumbnail_key(slug, vid)
        except Exception as e:  # noqa: BLE001 - 배경 업로드 실패해도 진행
            logger.warning("[music-test] 배경 업로드 실패(영상은 유효): %s", e)

        # 재렌더용: 테스트 오디오(mp3) + 트랙 메타(json)를 R2 믹스 경로에 업로드.
        # (music_rerender._load_mix 가 music_mix_key(slug, mix_id, mp3/json) 를 읽는다.)
        try:
            r2_storage.upload_music_mix(str(audio), slug, vid, ext="mp3")
            meta_path = work / "mix.json"
            meta_path.write_text(json.dumps({"tracks": tracks}, ensure_ascii=False), encoding="utf-8")
            r2_storage.upload_music_mix(
                str(meta_path), slug, vid, ext="json", content_type="application/json"
            )
        except Exception as e:  # noqa: BLE001 - 믹스 업로드 실패 시 재렌더만 불가(영상은 유효)
            logger.warning("[music-test] 믹스 오디오/메타 업로드 실패(재렌더 불가 가능): %s", e)

        # 검토 대기(pending)에 저장 → 검토대기 카드로 등록, 대표가 직접 삭제. slug=test_{timestamp}.
        try:
            from services import music_uploads
            music_uploads.record_pending(
                slug, vid, mp4_url=video_url, title_kr=preset["title_kr"],
                genre=preset.get("genre", ""), mood=key,
                thumbnail_r2_key=thumb_key, viz_spec=viz_spec,
            )
        except Exception as e:  # noqa: BLE001 - 큐 저장 실패해도 영상 URL 은 반환
            logger.warning("[music-test] 검토대기 저장 실패(영상은 유효): %s", e)

        logger.info("[music-test] 렌더 완료 engine=%s url=%s slug=%s", engine, video_url, slug)
        return {
            "video_url": video_url,
            "engine": engine,
            "mood": key,
            "duration": seconds,
            "title_kr": preset["title_kr"],
            "mix_id": vid,
            "slug": slug,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
