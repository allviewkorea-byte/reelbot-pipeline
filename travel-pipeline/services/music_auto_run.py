"""음악 채널 자동 회차(PR-2a) — 채널별 하루 N회 제작 → 유튜브 예약 공개.

백엔드 apscheduler(services/scheduler.py)가 1분마다 tick() 을 부른다. 외부 cron 설정이 필요 없다.

회차 규칙
  - 대상: AUTO_RUN_CHANNELS(기본 workout_music) 중 channel_status.is_active=true 인 채널.
    where(rooftop_music)는 목록에 없어 is_active 와 무관하게 절대 돌지 않는다.
  - 공개 시각 T = 그 채널의 공개 시(channel_config.publish_hours, 기본 [6, 18]) + 분(0~59).
    분은 (채널·날짜·회차) 해시로 정한다 — 매일·회차마다 달라 보이지만, 재시작해도 같은 T 가
    나온다(저장 없이 결정적). 하루 회차 수 = daily_cap(공개 시 개수를 넘지 않음).
  - 제작 시작 = T − 120분. 시작 시각이 지났고 T+3시간 전이면 시작, T+3시간이 지났으면 건너뜀.
  - 중복 방지: music_jobs.job_id(unique)에 회차 키 auto-{채널}-{YYYYMMDD}-{회차} 를 먼저 insert
    해서 선점한다. 이미 있으면(다른 인스턴스·재시작 전 프로세스) 실행하지 않는다.
    재시작 전에 시작했다가 끊긴 회차(queued/running 이고 마지막 갱신이 이 프로세스 시작 전)는
    조건부 PATCH 로 다시 선점해 이어간다(렌더까지 끝났으면 업로드만).

회차 실행
  ① 제작 = 수동 "곡 만들기"와 같은 경로(music_manual.start/run) — 운동 기본 조합·AI 배경
     이미지(#336 재사용 포함)·렌더·검토대기 적재까지 그대로.
  ② 렌더가 Remotion 이 아니면(frame_thumb_key 없음 = ffmpeg 폴백) 또는 video_url 이 http 가
     아니면 업로드하지 않고 실패로 기록한다(영상은 검토대기에 남는다).
  ③ 업로드 = 수동 "공개" 경로(music_dashboard.publish) 그대로 — 설명란 재조립·AI 고지 검사(#335)
     포함. mode=auto 면 private + publishAt=T(예약 공개), T 가 이미 지났으면 즉시 public.
     mode=semi 면 비공개 업로드. AI 표시는 그 채널 행의 synthetic_media.

장애 대비(2026-10-19 대표 승인)
  - 재시도: 곡 생성(Suno) 전에 실패한 회차는 10분 뒤 같은 회차 키로 다시(최대 3회). "다음 시도 +
    10분 < T" 일 때만 예약하고, 다시 띄울 때는 실패 행을 조건부 PATCH 로 재선점(중복 실행 0).
    Suno 호출 뒤 실패는 기존 복구 A~G 에 맡긴다.
  - 실패 사유 코드: claim 행 metadata.fail_reason — llm_unavailable / image_failed / upload_gate /
    upload / suno / render / busy / unknown.
  - 운동 배경 축: 회차마다 근력/유산소/워밍업 50/30/20 가중 랜덤(3연속 금지). 배경만 바꾼다.

모든 로그 접두사 [auto-run] — 채널·회차·T 포함.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
LEAD_MIN = 120            # 제작 시작 = T − 120분
LATE_LIMIT_MIN = 180      # T 를 3시간 넘긴 회차는 건너뜀
DEFAULT_PUBLISH_HOURS = [6, 18]
BUSY_RETRY_SEC = 120      # 수동 생성이 돌고 있으면 2분 뒤 다시
BUSY_MAX_WAIT_SEC = 3600  # 최대 1시간 대기 후 실패
JOB_TYPE = "auto_run"
RETRY_GAP_MIN = 10        # 이른 실패(곡 생성 전) 재시도 간격
MAX_RETRIES = 3


class RoundFailed(RuntimeError):
    """회차 실패 + 사유 코드(reason) + 곡 생성(Suno) 전 실패인지(early → 재시도 대상)."""

    def __init__(self, msg: str, reason: str = "unknown", *, early: bool = False):
        super().__init__(msg)
        self.reason = reason
        self.early = early

_STARTED_AT = datetime.now(timezone.utc)   # 이 프로세스 시작 시각 — 끊긴 회차 판별 기준
_LOCK = threading.Lock()
_RUNNING: set[str] = set()                 # 이 프로세스에서 실행 중인 회차 키
_LOGGED_SKIP: set[str] = set()             # "건너뜀" 로그 1회만
_SETTLED: set[str] = set()                 # 완료·실패가 확인된 회차(매 tick 재조회 생략)


WHERE_CHANNEL = "rooftop_music"
# 채널별 공개 시 기본값(channel_config.publish_hours 가 없을 때). where 는 08시대·21시대(대표 결정).
CHANNEL_DEFAULT_HOURS: dict[str, list[int]] = {WHERE_CHANNEL: [8, 21]}


def auto_run_channels() -> list[str]:
    """자동 회차 대상 채널(운동 + where). 각 채널은 channel_status.is_active 로 켜고 끈다.

    env MUSIC_AUTO_RUN_CHANNELS(쉼표)로 덮을 수 있다(예: 운동만 "workout_music").
    """
    raw = (os.getenv("MUSIC_AUTO_RUN_CHANNELS") or f"workout_music,{WHERE_CHANNEL}").strip()
    return [c.strip() for c in raw.split(",") if c.strip()]


def enabled() -> bool:
    return (os.getenv("MUSIC_AUTO_RUN") or "on").strip().lower() not in ("0", "off", "false", "no")


# ── 채널 상태 ─────────────────────────────────────────────────────────
def get_channel_state(channel: str) -> dict:
    """channel_status 한 행 → {is_active, mode, synthetic_media, daily_cap, track_count, publish_hours}.

    조회 실패·행 없음 → is_active=False(안전: 돌지 않음).
    """
    st = {"is_active": False, "mode": "semi", "synthetic_media": False, "daily_cap": 1,
          "track_count": 1, "publish_hours": list(CHANNEL_DEFAULT_HOURS.get(channel) or DEFAULT_PUBLISH_HOURS)}
    st["known"] = False
    url, key = _supabase_cfg()
    if not (url and key):
        return st
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/channel_status",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{channel}", "select": "*", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-run] channel_status 조회 실패 channel=%s: %s", channel, _http_err(e))
        return st
    st["known"] = True  # 대시보드: 조회 성공(False = 확인 불가 — "가동 꺼짐"과 구별). 행 없음 = 꺼짐
    if not rows:
        return st
    row = rows[0]
    st["updated_at"] = row.get("updated_at")  # 건너뜀 기록 판단용(가동을 T 이후에 켰으면 기록 안 함)
    st["is_active"] = bool(row.get("is_active"))
    st["mode"] = "auto" if row.get("mode") == "auto" else "semi"
    st["synthetic_media"] = bool(row.get("synthetic_media"))
    try:
        st["daily_cap"] = max(1, min(3, int(row.get("daily_cap") or 1)))
    except (TypeError, ValueError):
        pass
    try:
        st["track_count"] = max(1, min(100, int(row.get("track_count") or 1)))
    except (TypeError, ValueError):
        pass
    st["publish_hours"] = normalize_hours(
        (row.get("channel_config") or {}).get("publish_hours"), CHANNEL_DEFAULT_HOURS.get(channel),
    )
    return st


def normalize_hours(raw, default: list[int] | None = None) -> list[int]:
    """공개 시 목록(0~23 정수, 중복 제거·정렬). 비었거나 이상하면 기본 [6, 18]."""
    out: list[int] = []
    if isinstance(raw, list):
        for v in raw:
            try:
                h = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= h <= 23 and h not in out:
                out.append(h)
    return sorted(out) or list(default or DEFAULT_PUBLISH_HOURS)


# ── 회차 계산 ─────────────────────────────────────────────────────────
def _salt() -> str:
    return (os.getenv("MUSIC_AUTO_RUN_SALT") or "reelbot").strip()


def round_minute(channel: str, day: date, slot: int) -> int:
    """(채널·날짜·회차) → 0~59 분. 결정적이라 재시작해도 같은 값."""
    h = hashlib.sha256(f"{channel}|{day.isoformat()}|{slot}|{_salt()}".encode()).hexdigest()
    return int(h, 16) % 60


def round_key(channel: str, day: date, slot: int) -> str:
    return f"auto-{channel}-{day.strftime('%Y%m%d')}-{slot}"


def rounds_for_day(channel: str, day: date, hours: list[int], daily_cap: int) -> list[dict]:
    """그날의 회차 목록. slot 은 1부터, T·start 는 KST aware datetime."""
    out = []
    for i, hour in enumerate(sorted(hours)[: max(1, daily_cap)], start=1):
        t = datetime(day.year, day.month, day.day, hour, round_minute(channel, day, i), tzinfo=KST)
        out.append({
            "channel": channel, "day": day, "slot": i, "key": round_key(channel, day, i),
            "publish_at": t, "start_at": t - timedelta(minutes=LEAD_MIN),
        })
    return out


def _fmt(r: dict) -> str:
    return f"channel={r['channel']} 회차={r['slot']} T={r['publish_at'].strftime('%Y-%m-%d %H:%M')}KST"


def publish_at_rfc3339(t: datetime) -> str:
    """유튜브 status.publishAt 형식(UTC, ...Z)."""
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ── tick(1분마다) ─────────────────────────────────────────────────────
def tick(now: datetime | None = None) -> list[str]:
    """시작할 회차를 찾아 백그라운드로 띄운다. 띄운 회차 키 목록 반환(테스트용)."""
    if not enabled():
        return []
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    launched: list[str] = []
    for channel in auto_run_channels():
        st = get_channel_state(channel)
        if not st["is_active"]:
            continue
        # 0시대 공개는 제작이 전날 시작하므로 오늘·내일 회차를 같이 본다.
        for day in (now.date(), now.date() + timedelta(days=1)):
            for r in rounds_for_day(channel, day, st["publish_hours"], st["daily_cap"]):
                if now < r["start_at"]:
                    continue
                if now >= r["publish_at"] + timedelta(minutes=LATE_LIMIT_MIN):
                    if r["key"] not in _LOGGED_SKIP and not _claimed_row(r["key"]):
                        _LOGGED_SKIP.add(r["key"])
                        logger.warning("[auto-run] 회차 건너뜀(T+3시간 초과, 미실행) %s", _fmt(r))
                        _record_skip(r, st)
                    continue
                if _try_launch(r, st, now):
                    launched.append(r["key"])
    return launched


def _record_skip(r: dict, st: dict) -> None:
    """건너뛴 회차를 claim 행(failed·state=skipped)으로 남긴다 — 대시보드 상태등·연속 일수용(기록만).

    실행 여부는 위에서 이미 "안 함"으로 정해졌다. 가동 상태(channel_status.updated_at)가 그 회차 T 이후에
    바뀌었으면 T 시점엔 꺼져 있었을 수 있어 기록하지 않는다(로그만 — 꺼 둔 날을 사고로 세지 않게).
    """
    from services import music_jobs
    changed = _parse_dt(st.get("updated_at")) if st.get("updated_at") else None
    if changed is not None and changed > r["publish_at"]:
        logger.warning("[auto-run] 가동 상태가 T 이후 바뀜 → 건너뜀 기록 생략 %s", _fmt(r))
        return
    meta = {
        "channel": r["channel"], "slot": r["slot"], "day": r["day"].isoformat(),
        "publish_at": r["publish_at"].isoformat(), "start_at": r["start_at"].isoformat(),
        "state": "skipped", "fail_reason": "skipped",
    }
    music_jobs.record_skipped(r["key"], JOB_TYPE, channel=r["channel"], metadata=meta,
                              error=f"[자동 회차 {r['slot']} · T {r['publish_at'].strftime('%m-%d %H:%M')}] "
                                    "T+3시간까지 시작하지 못해 건너뜀")


def _claimed_row(key: str) -> dict | None:
    from services import music_jobs
    return music_jobs.get_job(key)


def _try_launch(r: dict, st: dict, now: datetime) -> bool:
    from services import music_jobs

    with _LOCK:
        if r["key"] in _RUNNING or r["key"] in _SETTLED:
            return False
    meta = {
        "channel": r["channel"], "slot": r["slot"], "day": r["day"].isoformat(),
        "publish_at": r["publish_at"].isoformat(), "start_at": r["start_at"].isoformat(),
        "state": "claimed",
    }
    resume: dict | None = None
    if music_jobs.claim_job(r["key"], JOB_TYPE, channel=r["channel"], metadata=meta):
        logger.warning("[auto-run] 회차 선점 → 제작 시작 %s (시작 예정 %s, 지금 %s)", _fmt(r),
                       r["start_at"].strftime("%H:%M"), now.strftime("%H:%M"))
    else:
        row = _claimed_row(r["key"])
        if not row:
            return False  # 조회 불가 → 이번 tick 은 건너뜀
        old_meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if row.get("status") == "failed":
            due = _retry_due(old_meta, r, now)
            if due is None:
                _SETTLED.add(r["key"])  # 재시도 예약 없음·T 지남 → 다시 돌리지 않는다
                return False
            if not due:
                return False  # 재시도 시각 전
            new_meta = {**old_meta, "state": "retrying", "retry_at": None}
            if not music_jobs.reclaim_failed_job(r["key"], row.get("updated_at"), new_meta):
                return False  # 다른 인스턴스가 먼저 가져감
            logger.warning("[auto-run] 이른 실패 재시도 %d/%d %s (직전 사유=%s)", int(old_meta.get("retries") or 0),
                           MAX_RETRIES, _fmt(r), old_meta.get("fail_reason") or "-")
        elif row.get("status") not in ("queued", "running"):
            _SETTLED.add(r["key"])  # 이미 끝남(완료) → 다시 돌리지 않는다
            return False
        elif not _stale(row):
            return False  # 다른 프로세스가 지금 돌리는 중
        elif not music_jobs.reclaim_job(r["key"], row.get("updated_at")):
            return False
        else:
            resume = old_meta
            logger.warning("[auto-run] 재시작 전 끊긴 회차 이어서 실행 %s (state=%s)", _fmt(r), resume.get("state"))
    with _LOCK:
        _RUNNING.add(r["key"])
    threading.Thread(target=_run_round_safe, args=(r, st, resume), name=f"auto-run-{r['key']}",
                     daemon=True).start()
    return True


def _parse_dt(v) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=KST)


def _retry_due(meta: dict, r: dict, now: datetime) -> bool | None:
    """실패 회차의 재시도 판단. None=재시도 없음(예약 없음·T 지남), False=아직, True=지금."""
    at = _parse_dt(meta.get("retry_at")) if meta.get("retry_at") else None
    if at is None or now >= r["publish_at"]:
        return None
    return now >= at


def next_retry_at(r: dict, retries: int, early: bool, now: datetime) -> datetime | None:
    """이른 실패면 10분 뒤 재시도 시각. 최대 3회, 그리고 "다음 시도 + 10분 < T" 일 때만."""
    if not early or retries >= MAX_RETRIES:
        return None
    at = now + timedelta(minutes=RETRY_GAP_MIN)
    if at + timedelta(minutes=RETRY_GAP_MIN) >= r["publish_at"]:
        return None
    return at


def _stale(row: dict) -> bool:
    """끊긴 회차 = 하트비트(updated_at) 10분 경과 + 이 프로세스 시작 전(복구 E 와 같은 기준).

    회차 실행 중에는 Heartbeat 가 1분마다 claim 행을 갱신하므로, 배포 중 두 서버가 겹쳐도
    살아 있는 회차를 새 서버가 가져가지 않는다.
    """
    from services import music_recovery
    try:
        ts = datetime.fromisoformat(str(row.get("updated_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return ts < _STARTED_AT and ts < datetime.now(timezone.utc) - timedelta(minutes=music_recovery.STALE_MIN)


def _run_round_safe(r: dict, st: dict, resume: dict | None) -> None:
    from services import music_jobs, music_recovery
    try:
        with music_recovery.Heartbeat(r["key"]):
            run_round(r, st, resume=resume)
    except Exception as e:  # noqa: BLE001
        reason = getattr(e, "reason", None) or "unknown"
        # RoundFailed 가 아니면 제작 시작 전(phase=pre_produce)에 난 예외만 이른 실패로 본다.
        early = bool(getattr(e, "early", r.get("phase") == "pre_produce"))
        meta = (music_jobs.get_job(r["key"]) or {}).get("metadata") or {}
        retries = int(meta.get("retries") or 0) if isinstance(meta, dict) else 0
        nxt = next_retry_at(r, retries, early, datetime.now(KST))
        patch = {"state": "failed", "error": str(e)[:300], "fail_reason": reason,
                 "retry_at": nxt.isoformat() if nxt else None}
        if nxt:
            patch["retries"] = retries + 1
        logger.warning("[auto-run] 회차 실패 %s reason=%s early=%s 재시도=%s: %s", _fmt(r), reason, early,
                       nxt.strftime("%H:%M") if nxt else "없음", e)
        music_jobs.merge_metadata(r["key"], patch)
        tail = f" — {nxt.strftime('%H:%M')} 재시도 {retries + 1}/{MAX_RETRIES}" if nxt else ""
        music_jobs.show_failed(
            r["key"], f"[자동 회차 {r['slot']} · T {r['publish_at'].strftime('%m-%d %H:%M')} · {reason}] {e}{tail}",
        )
    finally:
        with _LOCK:
            _RUNNING.discard(r["key"])


# ── 회차 실행 ─────────────────────────────────────────────────────────
def run_round(r: dict, st: dict, *, resume: dict | None = None, sleep=time.sleep) -> dict:
    """제작 → (폴백 검사) → 업로드. 실패는 예외(호출부가 실패 기록). 결과 dict 반환."""
    from services import music_jobs

    key = r["key"]
    music_jobs.update_job_step(key, "theme")
    mix_id = (resume or {}).get("mix_id") if (resume or {}).get("state") == "rendered" else None
    if mix_id:
        logger.warning("[auto-run] 렌더 완료분 재사용 → 업로드만 %s mix_id=%s", _fmt(r), mix_id)
    elif (resume or {}).get("state") == "producing" and (resume or {}).get("job_id"):
        # 제작 중에 끊긴 회차 — 곡은 이미 (일부) 만들어졌을 수 있다. Suno 를 다시 부르지 않고
        # 복구 E(music_recovery)가 그 제작 작업을 같은 곡으로 재개하길 기다렸다가 결과만 쓴다.
        mix_id = _await_recovered(r, resume["job_id"], sleep=sleep)
    else:
        mix_id = _produce(r, st, sleep=sleep)
    music_jobs.merge_metadata(key, {"state": "rendered", "mix_id": mix_id})
    music_jobs.update_job_step(key, "upload")
    up = _upload(r, st, mix_id)
    music_jobs.merge_metadata(key, {"state": "uploaded", **up})
    music_jobs.complete_job(key, mix_id=mix_id)
    logger.warning("[auto-run] 회차 완료 %s mix_id=%s video=%s privacy=%s publishAt=%s", _fmt(r),
                   mix_id, up.get("youtube_video_id"), up.get("privacy"), up.get("publish_at") or "-")
    return {"mix_id": mix_id, **up}


AWAIT_MAX_SEC = 3 * 3600


def pick_where_genre(channel: str, *, rng=None) -> str:
    """where 장르 랜덤(15개, 발라드만 2배 가중). 직전 2회차가 같은 장르면 그 장르는 뺀다(연속 3회 금지).

    직전 장르는 자동 회차 claim 행(metadata.genre, DB)에서 읽는다 — 재시작해도 이어진다.
    """
    import random as _r
    from services import music_jobs
    from services.music_where_image import WHERE_GENRES
    r = rng or _r
    recent = [((row.get("metadata") or {}).get("genre")) for row in music_jobs.list_recent_by_type(JOB_TYPE, channel, limit=2)]
    pool = list(WHERE_GENRES)
    if len(recent) == 2 and recent[0] and recent[0] == recent[1] and recent[0] in pool:
        pool.remove(recent[0])
    # K-발라드 가중치(대표 2026-10-29 "K-발라드도 넣어줘") — 발라드는 다른 장르의 2배 확률.
    weights = [WHERE_GENRE_WEIGHT.get(g, 1.0) for g in pool]
    return r.choices(pool, weights=weights, k=1)[0]


WHERE_GENRE_WEIGHT: dict[str, float] = {"ballad": 2.0}   # kcitypop 은 1(새 장르로 추가만)


def _await_recovered(r: dict, job_id: str, *, sleep) -> str:
    """끊긴 제작 작업(job_id)이 복구 E 로 완료되길 기다린다 → mix_id. 실패·시간 초과면 예외."""
    from services import music_jobs
    waited = 0
    while waited <= AWAIT_MAX_SEC:
        row = music_jobs.get_job(job_id) or {}
        if row.get("status") == "completed" and row.get("mix_id"):
            logger.warning("[auto-run] 끊긴 제작이 복구로 완료 → 업로드 %s mix_id=%s", _fmt(r), row["mix_id"])
            return row["mix_id"]
        if row.get("status") == "failed":
            reason = ((row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {}).get("fail_reason")
            raise RoundFailed(f"끊긴 제작 복구 실패: {row.get('error_message') or '-'}", reason or "unknown")
        sleep(60)
        waited += 60
    raise RoundFailed("끊긴 제작 복구 대기 시간 초과", "render")


def _produce(r: dict, st: dict, *, sleep) -> str:
    """수동 "곡 만들기" 경로로 1편 제작 → mix_id. 폴백 렌더·비 http 영상이면 예외."""
    from services import music_manual

    # where: 14장르 프리셋 경로(장르 id 를 mood 로) — 장르는 균등 랜덤·같은 장르 연속 3회 금지.
    # 운동: 기존 그대로(mood None → 운동 기본 조합).
    r["phase"] = "pre_produce"
    genre = pick_where_genre(r["channel"]) if r["channel"] == WHERE_CHANNEL else None
    bg_style = None
    if genre:
        # 배경 스타일 — 허용 장르면 MUSIC_WHERE_STREET_RATE(기본 0.4)로 거리 스냅, 아니면 건축 공간.
        from services import music_jobs as _mj
        from services import music_where_image as _mwi
        bg_style = _mwi.pick_style(genre)
        _mj.merge_metadata(r["key"], {"genre": genre, "bg_style": bg_style})
        logger.warning("[auto-run] where 장르 선택 %s genre=%s", _fmt(r), genre)
        logger.warning("[auto-image] style=%s genre=%s %s", bg_style, genre, _fmt(r))
    image_action = _pick_image_action(r)
    # 다른 생성(다른 채널 회차·수동)이 돌고 있으면 기다린다 — 상한은 그 회차 공개 시각 T까지
    # (T 가 이미 지났거나 가까우면 최소 BUSY_MAX_WAIT_SEC). 동시 1개 락은 그대로.
    limit = max((r["publish_at"] - datetime.now(KST)).total_seconds(), BUSY_MAX_WAIT_SEC)
    waited = 0
    while True:
        started = music_manual.start(
            genre, st["track_count"], None, channel=r["channel"], auto_image=True,
        )
        if started.get("ok"):
            break
        if waited >= limit:
            raise RoundFailed(f"다른 생성이 계속 진행 중이라 시작 못 함({waited // 60}분 대기)", "busy", early=True)
        logger.warning("[auto-run] 다른 생성 진행 중 → %d초 뒤 재시도 %s", BUSY_RETRY_SEC, _fmt(r))
        sleep(BUSY_RETRY_SEC)
        waited += BUSY_RETRY_SEC
    job_id = started["job_id"]
    r["phase"] = "producing"
    if image_action and job_id in music_manual._JOBS:
        music_manual._JOBS[job_id]["image_action"] = image_action  # run() 전에 — 배경 축만 바꾼다
    if bg_style and job_id in music_manual._JOBS:
        music_manual._JOBS[job_id]["image_style"] = bg_style  # where 배경 스타일(거리 스냅/건축 공간)
    logger.warning("[auto-run] 제작 시작 %s job=%s 곡수=%d", _fmt(r), job_id, st["track_count"])
    from services import music_jobs
    music_jobs.merge_metadata(r["key"], {"state": "producing", "job_id": job_id})
    music_manual.run(job_id)
    job = music_manual._JOBS.get(job_id) or {}
    if job.get("status") != "done" or not job.get("mix_id"):
        raise RoundFailed(f"제작 실패: {job.get('error') or job.get('status')}",
                          job.get("fail_reason") or "unknown", early=bool(job.get("early_fail")))
    if isinstance(job.get("image_review"), dict):
        r["image_ok"] = bool(job["image_review"].get("ok"))
    video_url = str(job.get("video_url") or "")
    if not video_url.startswith("http"):
        raise RoundFailed(f"영상 URL 이 http 가 아님({video_url[:80]}) — 업로드 안 함(검토대기에 남김)", "render")
    if not job.get("frame_thumb_key"):
        raise RoundFailed("Remotion 렌더 실패(ffmpeg 폴백, 로고 없음) — 업로드 안 함(검토대기에 남김)", "render")
    logger.warning("[auto-run] 제작 완료 %s mix_id=%s 배경=%s", _fmt(r), job["mix_id"],
                   "재사용" if (job.get("image_review") or {}).get("reused") else
                   ("생성" if (job.get("image_review") or {}).get("ok") else "없음"))
    return job["mix_id"]


def _pick_image_action(r: dict) -> str | None:
    """운동 회차 배경 축(근력/유산소/워밍업 50/30/20, 3연속 금지) → 대표 action. where·실패 → None.

    직전 축은 R2 music-auto-bg/_recent_workout.json 에서 읽는다(재시작해도 이어진다).
    """
    from services.music_workout_style import is_workout_channel
    if not is_workout_channel(r["channel"]):
        return None
    try:
        from services import music_auto_image as mai
        from services import music_jobs
        axis = mai.pick_workout_axis(mai.read_recent().get("axes"))
        music_jobs.merge_metadata(r["key"], {"bg_axis": axis})
        logger.warning("[auto-run] 운동 배경 축 선택 %s axis=%s", _fmt(r), axis)
        return mai.AXIS_ACTION[axis]
    except Exception as e:  # noqa: BLE001 - 축 선택 실패 → 기존 그대로(근력)
        logger.warning("[auto-run] 운동 배경 축 선택 실패(기존 그대로) %s: %s", _fmt(r), e)
        return None


def _upload(r: dict, st: dict, mix_id: str, now: datetime | None = None) -> dict:
    """수동 "공개" 경로(music_dashboard.publish) 재사용. mode=auto → 예약 공개, semi → 비공개."""
    from fastapi import HTTPException

    from api.routes import music_dashboard as md

    now = now or datetime.now(timezone.utc)
    if st["mode"] != "auto":
        body = md.PublishBody(synthetic_media=st["synthetic_media"], privacy="private", require_remotion=True)
        privacy, pub_at = "private", None
    elif r["publish_at"] > now + timedelta(minutes=2):
        pub_at = publish_at_rfc3339(r["publish_at"])
        body = md.PublishBody(synthetic_media=st["synthetic_media"], publish_at=pub_at, require_remotion=True)
        privacy = "private"
    else:
        logger.warning("[auto-run] 제작이 T 이후 완료 → 즉시 공개 %s", _fmt(r))
        body = md.PublishBody(synthetic_media=st["synthetic_media"], require_remotion=True)
        privacy, pub_at = "public", None
    logger.warning("[auto-run] 업로드 시작 %s mix_id=%s privacy=%s publishAt=%s AI표시=%s",
                   _fmt(r), mix_id, privacy, pub_at or "-", st["synthetic_media"])
    try:
        res = md.publish(mix_id, body)
    except HTTPException as e:
        # 400 = 공개 게이트(썸네일·렌더 실패 표식 등). 배경 이미지가 실패한 영상이면 image_failed.
        reason = "upload" if e.status_code != 400 else ("image_failed" if r.get("image_ok") is False else "upload_gate")
        raise RoundFailed(f"업로드 실패({e.status_code}): {e.detail}", reason) from e
    return {"youtube_video_id": res.get("youtube_video_id"), "youtube_url": res.get("youtube_url"),
            "privacy": privacy, "publish_at": pub_at}
