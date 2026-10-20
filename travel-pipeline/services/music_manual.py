"""수동 영상 생성(#26) — 즉석 주제 1개 → 진짜 음원 1곡 → 가사·viz_spec → 풀 렌더 → 검토 큐.

대표가 버튼으로 수동 실행한 1곡을 **검토 큐에 정식 영상(status=pending)으로 적재**한다
(#25 풀 테스트의 persist=False 폐기 → persist=True). 일반 cron 제작과 동일한 파이프라인
(music_produce.produce: 가사 GPT → suno 보컬 → 마스터 → 믹스)을 1곡으로 돌리고, make_video
가 gpt-image 배경 + Remotion 풀 렌더 + record_pending(큐 저장)까지 수행한다. 유튜브 업로드는
하지 않는다(대표가 큐에서 썸네일 업로드 후 공개).

수 분~수십 분 걸리므로 BackgroundTasks 로 비동기 실행 + 인메모리 job 상태 폴링. 동시 1개 제한.
JobManager 는 인메모리(재시작 시 소실).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
import uuid

# 장르 체계 SSOT(#45) — 14장르 프리셋·기본값. music_genres 는 의존성 0(순환 안전).
from services import music_genres

logger = logging.getLogger(__name__)

_DEFAULT_MOOD = music_genres.DEFAULT_GENRE

# 진행 단계(프론트 표시용 한국어): 주제 → 음원 → 가사 → 렌더 → 완료.
# 인메모리 job 저장소 + 동시 1개 제한 락.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active_job: str | None = None


def available_moods() -> list[str]:
    return list(music_genres.GENRE_IDS)


# #42 수동 생성 곡수 1~100(범위 밖 클램프). 미지정 → 1(기존 동작 = 회귀 0).
_TRACK_MIN, _TRACK_MAX = 1, 100


def _clamp_track_count(n) -> int:
    try:
        return max(_TRACK_MIN, min(_TRACK_MAX, int(n)))
    except (TypeError, ValueError):
        return 1


def _workout_default_combo(tag_combo: dict | None, channel: str | None) -> dict | None:
    """운동 채널인데 tag_combo 가 없거나 비어 있으면 {"action": "workout"} 으로 채운다.

    칩도 "어떨때"도 안 고르면 프론트가 tag_combo 를 빼고 mood="citypop" 만 보낸다. 그대로 두면
    mood 프리셋(시티팝)·suno_config("citypop") 고정 태그로 떨어져 운동 채널에 시티팝이
    만들어진다(2026-10 실측). action 을 채우면 smart_random → refine_combo(운동 풀) 경로를 탄다.
    where(미지정 포함)·운동 채널의 대표 선택(칩/어떨때)은 원본 그대로 돌려준다(회귀 0).
    """
    from services.music_workout_style import is_workout_channel

    if not is_workout_channel(channel):
        return tag_combo
    if isinstance(tag_combo, dict) and any(tag_combo.values()):
        return tag_combo
    return {"action": "workout"}


def _build_theme(
    mood: str, track_count: int = 1, tag_combo: dict | None = None,
    *, channel: str | None = None,
) -> dict:
    """channel: 채널 축(4단계). theme 에 실어 보내면 music_video.py 를 수정하지 않고도
    해시태그·본문 Copyright 가 채널을 알 수 있다. None → where(기존 동작)."""
    # 운동 채널은 어떤 경로로 들어와도 mood 프리셋(시티팝)으로 새지 않게 한 번 더 막는다.
    tag_combo = _workout_default_combo(tag_combo, channel)
    if tag_combo:
        from services import music_tags
        has_chips = any(tag_combo.get(k) for k in ("genre", "situation", "emotion", "tempo", "format", "charm"))
        if not has_chips:
            from services import music_workout_style
            tag_combo = music_tags.smart_random(tag_combo)
            # start() 에서 이미 보정된 combo 가 오면 여기 분기는 안 탄다(칩이 차 있음).
            # 다른 경로로 들어온 combo 를 위한 동일 보정(멱등).
            tag_combo = music_workout_style.refine_combo(tag_combo, channel=channel)
        style = music_tags.tags_to_suno_style(tag_combo)
        instrumental = music_tags.is_instrumental(tag_combo)
        action = tag_combo.get("action") or ""
        genres = tag_combo.get("genre") or []
        genre_label = ", ".join(genres[:2]) if genres else "custom"
        lyric_tone = ""
        if action == "sleep" and not instrumental:
            lyric_tone = "잔잔하고 차분한, 잠들기 좋은, 느린, 위로하는 톤. 신나거나 빠른 분위기 금지."
        elif action == "baby_sleep" and not instrumental:
            lyric_tone = "자장가 톤, 아기에게 들려주는 부드럽고 따뜻한 가사. 느리고 반복적인 리듬."
        elif action == "focus" and not instrumental:
            lyric_tone = "차분하고 집중에 방해되지 않는 톤. 가사는 최소한으로, 반복적이고 단순하게."
        # 운동 채널(strength/cardio) — 가사 톤을 운동 톤으로. warmup·where 는 위 값 그대로.
        from services import music_workout_style as _mws
        lyric_tone = _mws.lyric_tone(action, channel=channel) or lyric_tone
        summary_kr = music_tags.combo_summary_kr(tag_combo)
        return {
            "slug": f"manual_{uuid.uuid4().hex[:12]}",
            "title_kr": summary_kr or "태그 조합",
            "genre": genre_label,
            "situation": action,
            "mood": action or "custom",
            "type": "instrumental" if instrumental else "vocal",
            "style_prompt": style,
            "lyric_tone": lyric_tone,
            "track_count": _clamp_track_count(track_count),
            "tag_combo": tag_combo,
            "channel": channel,
        }
    preset = music_genres.preset(mood)
    theme = {
        "slug": f"manual_{uuid.uuid4().hex[:12]}",
        "title_kr": preset["title_kr"],
        "genre": preset["genre"],
        "situation": preset["situation"],
        "mood": preset["mood"],
        "type": "vocal",
        "style_prompt": preset["style_prompt"],
        "lyric_tone": preset["lyric_tone"],
        "track_count": _clamp_track_count(track_count),
        "channel": channel,
    }
    # where 자동 회차(채널 'rooftop_music' 명시)만 장르 id 를 실어 해시태그·배경 이미지가 장르를 알게 한다.
    # where 수동 화면(채널 None)은 키 자체를 넣지 않는다(기존 theme 그대로).
    if channel == "rooftop_music":
        theme["genre_id"] = music_genres.normalize_mood_key(mood)
    return theme


def start(
    mood: str | None = None, track_count: int | None = None, tag_combo: dict | None = None,
    *, channel: str | None = None, auto_image: bool | None = None,
) -> dict:
    """수동 영상 생성 1개 시작(동시 1개 제한). {ok, job_id} 또는 {ok:False, error, busy_job}.

    track_count(#42): 영상에 넣을 곡수 1~100(미지정→1). 곡수 = Suno 호출 수 = 영상 길이(#40).
    tag_combo(③-A): 8축 태그 조합. 있으면 mood 무시, 태그 기반 style 생성.
    auto_image(PR-1): 운동 채널 배경 이미지 자동 생성. 운동 채널은 기본 ON(False 만 끔),
      where 는 값과 무관하게 항상 OFF(기존 동작).
    """
    global _active_job
    from services.music_auto_image import wants_auto_image
    auto = wants_auto_image(channel, auto_image)
    key = music_genres.normalize_mood_key(mood or _DEFAULT_MOOD)
    tc = _clamp_track_count(track_count if track_count is not None else 1)
    # 운동 채널 + 칩·어떨때 미선택 → {"action": "workout"}(아래 랜덤 경로가 운동 풀로 채운다).
    # 이게 없으면 mood 기본값(citypop) 프리셋으로 떨어진다. where 는 무변경.
    tag_combo = _workout_default_combo(tag_combo, channel)
    # 랜덤 경로: 칩 비었으면 미리 채워 metadata에 반영(카드에 채워진 칩 표시).
    if tag_combo:
        has_chips = any(tag_combo.get(k) for k in ("genre", "situation", "emotion", "tempo", "format", "charm"))
        if not has_chips:
            from services import music_tags, music_workout_style
            tag_combo = music_tags.smart_random(tag_combo)
            # 운동 채널 보정(5단계 B-1) — smart_random 은 action별 기본값이 sleep·
            # baby_sleep·focus 셋뿐이라 workout 에 dream pop·lights_off·peaceful 을
            # 넣는다. **칩을 하나도 안 고른 경우에만** 부른다(대표 선택은 보존).
            tag_combo = music_workout_style.refine_combo(tag_combo, channel=channel)
    with _LOCK:
        if _active_job and _JOBS.get(_active_job, {}).get("status") == "running":
            return {"ok": False, "error": "이미 영상 생성이 진행 중입니다. 완료 후 다시 시도하세요.", "busy_job": _active_job}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "step": "주제",
            "mood": key, "track_count": tc, "video_url": None, "mix_id": None, "error": None,
            "cancelled": False,
            "created_at": time.time(),
            "tag_combo": tag_combo,
            "channel": channel,  # run() 이 produce 로 전달(None → where)
            "auto_image": auto,
        }
        _active_job = job_id
    # 복구 F — 지난 작업에서 R2 저장이 실패해 보류된 Suno 곡이 있으면 백그라운드로 재취득(비차단).
    try:
        from services import music_recovery
        threading.Thread(target=music_recovery.reacquire_pending_stores, name="reacquire", daemon=True).start()
    except Exception:  # noqa: BLE001
        pass
    meta = {"mood": key, "track_count": tc}
    if tag_combo:
        meta["tag_combo"] = tag_combo
    if auto:
        meta["auto_image_requested"] = True
    try:
        from services import music_jobs
        music_jobs.start_job("manual_render", job_id=job_id, metadata=meta, channel=channel)
    except Exception as e:  # noqa: BLE001
        logger.debug("[music-manual] job 추적 시작 실패(무시): %s", e)
    return {"ok": True, "job_id": job_id}


def cancel(job_id: str) -> dict:
    """진행 중 job 취소 요청(#26-C). 현재 스텝(Suno·렌더)은 완료되나 큐 적재 없이 종료한다.

    백그라운드 스레드는 강제 종료 불가 → 협조적 취소: 플래그를 세우고 status='cancelled' 로 바꾼다.
    run() 이 렌더 직전 플래그를 보고 early return → record_pending 미실행 → 검토 큐에 안 쌓인다.
    """
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "job 없음"}
        if job["status"] != "running":
            return {"ok": False, "error": f"취소 불가 상태: {job['status']}"}
        job["cancelled"] = True
        job["status"] = "cancelled"
    try:
        from services import music_jobs
        music_jobs.fail_job(job_id, "사용자 취소")
    except Exception:  # noqa: BLE001 - 추적 실패는 무시
        pass
    logger.info("[music-manual] 취소 요청 수신 job=%s", job_id)
    return {"ok": True}


def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    st = {k: job[k] for k in ("job_id", "status", "step", "mood", "video_url", "mix_id", "error")}
    if "image_review" in job:  # 운동 채널 AI 이미지 검수 결과(있을 때만 — where 응답 무변경)
        st["image_review"] = job["image_review"]
    return st


def run(job_id: str) -> None:
    """백그라운드 실행체 — produce(1곡) → make_video(persist=True) → 검토 큐 적재."""
    global _active_job
    job = _JOBS.get(job_id)
    if not job:
        return

    from services import music_jobs

    # 한국어 표시 단계 → 표준 단계(music_jobs.STEPS) 매핑(파이프라인 시각화용).
    _CANON = {"주제": "theme", "음원": "vocal", "가사": "lyrics", "음원·믹스": "mix", "렌더": "video", "이미지": "video"}

    def _step(name: str) -> None:
        job["step"] = name
        logger.info("[music-manual] job=%s step=%s", job_id, name)
        canon = _CANON.get(name)
        if canon:
            try:
                music_jobs.update_job_step(job_id, canon)
            except Exception:  # noqa: BLE001 - 추적 실패는 무시
                pass

    def _produce_progress(msg: str) -> None:
        if "가사" in msg:
            _step("가사")
        elif "마스터" in msg or "믹스" in msg:
            _step("음원·믹스")
        else:
            _step("음원")

    img_dir: str | None = None
    hb = None
    cp = None
    try:
        from services import music_produce, music_recovery, music_video, music_viz_analyzer, music_workout_style

        tc = _clamp_track_count(job.get("track_count", 1))
        theme = _build_theme(
            job["mood"], tc, tag_combo=job.get("tag_combo"), channel=job.get("channel"),
        )
        slug = theme["slug"]
        # 복구 A·E — 주제·곡수를 먼저 남기고(재시작 후에도 같은 주제로 재개), 1분 하트비트 시작.
        cp = music_recovery.Checkpoint(job_id, {
            "kind": "manual", "slug": slug, "theme": music_recovery._theme_brief(theme),
            "track_count": tc, "minutes": 3.5, "channel": job.get("channel"),
            "auto_image": bool(job.get("auto_image")),
            "genre_id": None if job.get("tag_combo") else job.get("mood"),
            # 재시작 재개(E)가 같은 배경 축·스타일로 다시 만들게(자동 회차가 run() 전에 주입).
            "image_action": job.get("image_action"), "bg_style": job.get("image_style"),
        })
        cp.save()
        hb = music_recovery.Heartbeat(job_id).__enter__()

        bg_path: str | None = None
        video: dict | None = None
        try:
            _step("음원")
            # 실제 제작: 가사(GPT) → suno 보컬 N곡 → 마스터 → 믹스. 일반 cron 과 동일(#42 곡수 N).
            # #46: 수동 무드 키 = 14장르 id → 고정 태그·instrumental·재활용 적용.
            result = music_produce.produce(
                slug, n=tc,
                genre_theme=theme["genre"], base_style=theme["style_prompt"],
                style_prompt=theme["style_prompt"], track_type=theme.get("type", "vocal"),
                lyric_tone=theme["lyric_tone"], minutes=3.5,
                genre_id=None if job.get("tag_combo") else job["mood"],
                action=(job.get("tag_combo") or {}).get("action") or "",
                channel=job.get("channel"),
                # 운동 채널만 운동 소재 풀(플랜 LLM 참고). where 는 None → 기존 기본 풀 그대로.
                sub_theme_pool=music_workout_style.subtheme_pool(
                    (job.get("tag_combo") or {}).get("action"), channel=job.get("channel"),
                ),
                progress=_produce_progress,
                checkpoint=cp,
            )
            mix = result.get("mix")
            # 영상 언어(#345, 전 곡 같은 값) — 제목·해시태그·태그가 영어/연주 키워드 비중을 정한다(메타데이터만).
            _langs = [t.get("language") for t in (result.get("produced") or []) if t.get("language")]
            if _langs:
                theme["video_language"] = max(set(_langs), key=_langs.count)
            if not mix or not mix.get("mp3_url"):
                raise RuntimeError("믹스 생성 실패(음원 없음).")
            cp.set_stage("rendering", mix_id=mix.get("mix_id"))

            # #26-C 취소 체크 — 음원 생성까지 끝났어도 렌더 시작 전 취소면 큐 적재 없이 종료.
            if job.get("cancelled"):
                logger.info("[music-manual] 취소됨 → 렌더 생략 job=%s", job_id)
                return

            # 운동 채널 — 렌더 **전에** 배경 이미지를 만들어 렌더 1회로 끝낸다(PR-1).
            # 생성·검수 실패면 bg_path=None → 아래는 기존과 똑같이 블랙 배경 렌더(반자동).
            if job.get("auto_image"):
                _step("이미지")
                from services import music_auto_image
                img_dir = tempfile.mkdtemp(prefix="autoimg_")
                # image_action: 자동 회차가 고른 운동 배경 축의 대표 action(배경만 — 음악·제목은 그대로).
                bg_path, job["image_review"] = music_auto_image.prepare_for_render(
                    job_id, job.get("image_action") or (theme.get("tag_combo") or {}).get("action"), img_dir,
                    channel=job.get("channel"), genre=None if job.get("tag_combo") else job.get("mood"),
                    style=job.get("image_style"),
                )
                # where 자동 회차는 검은 배경 발행 금지 — 폴백까지 못 구하면 렌더 전에 멈춘다.
                if not bg_path and music_auto_image.is_where_auto(job.get("channel")):
                    raise music_auto_image.NoBackground(
                        "where 배경을 구하지 못함(장르·전 장르 보관함·기존 배경 모두 없음) — 렌더·업로드 안 함",
                    )
                if job.get("cancelled"):
                    logger.info("[music-manual] 취소됨 → 렌더 생략 job=%s", job_id)
                    return

            _step("렌더")
            viz_spec = music_viz_analyzer.analyze_song(theme, mix)
            # tag_combo 경로: LLM 한국어 제목으로 title_kr 업그레이드(카드·영상 표시용).
            if theme.get("tag_combo"):
                try:
                    from services import music_meta
                    ko_copy, _ = music_meta._generate_title_copy_tag(theme)
                    if ko_copy:
                        theme["title_kr"] = ko_copy
                except Exception:  # noqa: BLE001
                    pass
            cp.update_theme(theme)  # 재시도·재개가 같은 제목으로 렌더하게
            # 일반 cron 과 동일: gpt-image 배경 + Remotion 풀 렌더 + record_pending(검토 큐 적재).
            if bg_path:
                video = music_video.make_video(
                    theme, mix, viz_spec=viz_spec, persist=True, background_path=bg_path,
                )
            else:
                video = music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True)
            # 복구 B — 폴백(로고 없음)·로컬 경로·밀착 시트 로고 누락이면 렌더 실패로 본다.
            chk = music_recovery.check_render(video, channel=job.get("channel"))
            if not chk["ok"]:
                raise music_recovery.RenderFailed(chk["reason"], video)
            music_jobs.merge_metadata(job_id, {"render_check": chk})
        except Exception as e:  # noqa: BLE001
            # 복구 C — 곡을 하나라도 확보했으면 영상 단계만 다시(같은 곡·주제·가사, Suno 0회).
            # 배경 없음(where)은 렌더를 다시 해도 같은 결과라 복구하지 않는다.
            from services.music_auto_image import NoBackground
            if job.get("cancelled") or not cp.tracks or isinstance(e, NoBackground):
                raise
            logger.warning("[music-manual] 영상 단계 실패 → 복구 시도 job=%s: %s", job_id, e)
            video, chk = music_recovery.recover_video(
                cp.snapshot(), job_id=job_id, first_error=e, bg_path=bg_path, step=_step,
            )

        job["video_url"] = video.get("video_url")
        job["mix_id"] = video.get("video_id")
        # 자동 회차(PR-2a)가 폴백 렌더(첫프레임 없음)를 거르는 데 쓴다. 응답·DB 무변경.
        job["frame_thumb_key"] = video.get("frame_thumb_key")
        # 채널 보정 — record_pending 은 렌더 경로(music_video, 수정 금지)에서 불려 채널을
        # 못 받는다. 렌더를 시킨 이쪽이 mix_id 로 사후에 박는다. best-effort.
        if job.get("channel") and job.get("mix_id"):
            try:
                from services import music_uploads
                music_uploads.set_channel(job["mix_id"], job["channel"])
            except Exception as e:  # noqa: BLE001
                logger.warning("[music-manual] 채널 보정 실패(무시): %s", e)
        # 이미지를 대표 업로드와 같은 자리(thumbnail_r2_key)에 연결 — 큐 행이 생긴 렌더 뒤에만 가능.
        if bg_path and job.get("mix_id"):
            from services import music_auto_image
            att = music_auto_image.attach_after_render(
                slug, job["mix_id"], bg_path, video, channel=job.get("channel"),
            )
            if att.get("error"):
                job["image_review"] = {**job.get("image_review", {}), "ok": False,
                                       "summary": f"이미지 연결 실패: {att['error'][:120]}"}
        cp.set_stage("done", mix_id=job["mix_id"])
        job["status"] = "done"
        _step("완료")
        try:
            music_jobs.complete_job(job_id, mix_id=job["mix_id"])
        except Exception:  # noqa: BLE001
            pass
        logger.info("[music-manual] 완료 job=%s mix_id=%s url=%s", job_id, job["mix_id"], job["video_url"])
    except Exception as e:  # noqa: BLE001 - 실패 원인 폴링으로 전달
        job["status"] = "error"
        job["error"] = str(e)[:300]
        # 실패 가시화(F) — 사유 코드 + Suno 호출 전 실패인지(자동 회차 재시도 판단).
        job["early_fail"] = cp is None or not (cp.tracks or cp.task_ids)
        job["fail_reason"] = fail_reason_of(e, suno_called=not job["early_fail"])
        try:
            music_jobs.fail_job(job_id, str(e))
            music_jobs.merge_metadata(job_id, {"fail_reason": job["fail_reason"]})
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[music-manual] 실패 job=%s reason=%s: %s", job_id, job["fail_reason"], e)
    finally:
        if hb is not None:
            hb.__exit__(None, None, None)
        if img_dir:
            shutil.rmtree(img_dir, ignore_errors=True)
        with _LOCK:
            if _active_job == job_id:
                _active_job = None


def fail_reason_of(e: BaseException, *, suno_called: bool) -> str:
    """실패 사유 코드: upload_gate(배경 없음) / render / llm_unavailable / suno / unknown."""
    from services import music_llm_fallback, music_recovery
    from services.music_auto_image import NoBackground
    if isinstance(e, NoBackground):
        return "upload_gate"
    if isinstance(e, music_recovery.RenderFailed) or "렌더 실패" in str(e):
        return "render"
    if music_llm_fallback.is_llm_unavailable(e):
        return "llm_unavailable"
    return "suno" if suno_called else "unknown"
