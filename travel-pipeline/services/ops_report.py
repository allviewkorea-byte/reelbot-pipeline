"""매일 점검 리포트(대표 2026-10-28 "A 방식": 릴봇이 스스로 점검 → 대시보드 카드).

매일 09:30 KST(음악 자동 제작이 끝난 뒤) Vercel 크론 → POST /api/system/daily-report/run.
  1) collect: 서비스 상태(system_status) · 채널 가동 상태 · 지난 24시간 음악 작업/업로드 · 인스타 컬렉션
  2) summarize: Claude 가 한국어로 "이상 없음 / 확인 필요 N가지(원인·제안)" — 실패하면 규칙 요약
  3) ops_reports 에 날짜별 1행(멱등 — 같은 날 다시 돌리면 덮어씀)
화면: GET /api/system/daily-report(최신) → 시스템 화면·음악 화면 상단 카드.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
TABLE = "ops_reports"
MUSIC_CHANNELS = {"workout_music": "2주안에몸매만들기(운동)", "rooftop_music": "where(음악)"}
STATUS_CHANNELS = {**MUSIC_CHANNELS, "baekgom": "백곰의 실화보고서"}


def _rest(table: str, method: str = "GET", **kw) -> list[dict]:
    from services import insta_refs
    return insta_refs.rest(table, method, **kw)


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - 한 항목 실패가 리포트 전체를 막지 않게
        logger.warning("[ops-report] 수집 실패: %s", str(e)[:200])
        return default


def collect(now: datetime | None = None) -> dict:
    """지난 24시간 운영 데이터."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat()

    def system():
        from api.routes.system import system_status
        st = system_status()
        return {k: v for k, v in st.items() if isinstance(v, dict)}

    def channels():
        rows = _rest("channel_status", params={"select": "channel_id,is_active,mode,daily_cap"})
        return {r["channel_id"]: {"name": STATUS_CHANNELS.get(r["channel_id"], r["channel_id"]),
                                  "active": bool(r.get("is_active")), "mode": r.get("mode"),
                                  "daily_cap": r.get("daily_cap")}
                for r in rows if r.get("channel_id")}

    def jobs():
        rows = _rest("music_jobs", params={"select": "job_id,type,status,step,error_message,metadata,created_at",
                                           "created_at": f"gte.{since}", "order": "created_at.desc", "limit": "50"})
        return [{"job_id": r.get("job_id"), "type": r.get("type"), "status": r.get("status"), "step": r.get("step"),
                 "channel": (r.get("metadata") or {}).get("channel"), "error": (r.get("error_message") or "")[:200],
                 "at": r.get("created_at")} for r in rows]

    def uploads():
        rows = _rest("music_uploads", params={"select": "channel,status,title_kr,youtube_url,uploaded_at",
                                              "uploaded_at": f"gte.{since}", "order": "uploaded_at.desc", "limit": "30"})
        return [{"channel": r.get("channel"), "status": r.get("status"), "title": r.get("title_kr"),
                 "url": r.get("youtube_url"), "at": r.get("uploaded_at")} for r in rows]

    def collections():
        rows = _rest("ig_collections", params={"select": "id,status,error,cost_usd,theme,created_at",
                                               "created_at": f"gte.{since}", "order": "created_at.desc", "limit": "20"})
        return [{"id": r.get("id"), "status": r.get("status"), "error": (r.get("error") or "")[:160],
                 "concept": (r.get("theme") or {}).get("concept"), "cost_usd": r.get("cost_usd")} for r in rows]

    def youtube():
        from services import yt_stats
        return yt_stats.report_summary(now)

    def credits():
        from services import music_auto_run as ar
        from services import music_dashboard_summary as mds
        from services import music_ops_log
        states = {ch: ar.get_channel_state(ch) for ch in MUSIC_CHANNELS}
        return mds.credit_view(mds.fetch_suno_balance(), states, music_ops_log.read_credit_snapshots())

    return {"since": since, "until": now.isoformat(), "system": _safe(system, {}), "channels": _safe(channels, {}),
            "music_jobs": _safe(jobs, []), "uploads": _safe(uploads, []), "collections": _safe(collections, []),
            "youtube": _safe(youtube, {}), "suno_credits": _safe(credits, {})}


# ── 요약 ──────────────────────────────────────────────────────────────────
_SYSTEM = (
    "You are the operations reviewer of ReelBot, an automated YouTube/Instagram content factory run by one Korean "
    "founder. Given the last 24 hours of data, write a short daily check in Korean for a non-developer. "
    "Rules: judge only from the data; if something is not in the data, do not invent it. A channel that is not "
    "active (active=false) producing nothing is normal. Failed jobs, missing uploads for an active channel, service "
    "errors (status error/warn), low Suno credits, and YouTube performance drops are issues. Keep each line short. "
    'Return ONE JSON object: {"level": "ok|warn|error", "headline": "<한 줄 요약>", '
    '"issues": [{"title": "<무엇이 문제>", "cause": "<데이터로 본 원인>", "suggestion": "<대표가 할 일 또는 '
    'Claude Code에 맡길 일>"}], "good": ["<잘 된 점, 최대 3개>"]} — issues 최대 5개, 없으면 빈 배열.'
)


def credit_issue(data: dict) -> dict | None:
    """Suno 크레딧 경고(규칙 — AI 요약과 상관없이 항상 맨 위). 다음 회차분 미만=error, N일치 미만=warn."""
    c = data.get("suno_credits") or {}
    if c.get("level") == "red":
        return {"level": "error", "title": f"Suno 크레딧 부족 — 잔액 {c.get('balance')}",
                "cause": f"다음 회차에 필요한 {c.get('one_round')} 크레딧보다 적어 오늘 제작이 멈춰요",
                "suggestion": "sunoapi.org 에서 지금 충전하세요(충전하면 그날 회차는 공개 시각 전까지 자동 재시도)"}
    if c.get("level") == "yellow":
        return {"level": "warn", "title": f"Suno 크레딧 약 {c.get('days_left')}일치 남음 — 잔액 {c.get('balance')}",
                "cause": f"하루 사용량 약 {c.get('daily')} 기준",
                "suggestion": "며칠 안에 sunoapi.org 에서 충전하세요"}
    return None


def apply_credit_issue(summary: dict, data: dict) -> dict:
    """요약 맨 앞에 크레딧 경고를 넣고 등급을 올린다(이미 같은 내용이 있으면 중복 제거)."""
    ci = credit_issue(data)
    if not ci:
        return summary
    level = ci.pop("level")
    issues = [i for i in summary.get("issues") or [] if "크레딧" not in (i.get("title") or "")]
    rank = {"ok": 0, "warn": 1, "error": 2}
    out = {**summary, "issues": ([ci] + issues)[:5]}
    if rank[level] > rank.get(summary.get("level"), 0):
        out["level"] = level
    if summary.get("level") == "ok" or not summary.get("issues"):
        out["headline"] = ci["title"]
    return out


def rule_summary(data: dict) -> dict:
    """LLM 이 실패했을 때의 규칙 요약."""
    issues = []
    for name, st in (data.get("system") or {}).items():
        if st.get("status") in ("error", "warn"):
            issues.append({"title": f"{name} 상태 {st.get('status')}", "cause": st.get("message") or "",
                           "suggestion": "시스템 화면에서 확인"})
    failed = [j for j in data.get("music_jobs") or [] if j.get("status") == "failed"]
    if failed:
        issues.append({"title": f"음악 작업 실패 {len(failed)}건", "cause": failed[0].get("error") or "",
                       "suggestion": "시스템 화면 오류 목록 확인"})
    uploaded = {u.get("channel") for u in data.get("uploads") or []}
    for cid, ch in (data.get("channels") or {}).items():
        if cid in MUSIC_CHANNELS and ch.get("active") and cid not in uploaded:
            issues.append({"title": f"{ch['name']} 24시간 업로드 없음", "cause": "가동 중인데 업로드 기록이 없음",
                           "suggestion": "노드그래프·오류 목록 확인"})
    level = "error" if any("error" in i["title"] for i in issues) else ("warn" if issues else "ok")
    return {"level": level, "headline": "이상 없음" if not issues else f"확인 필요 {len(issues)}가지",
            "issues": issues[:5], "good": [], "source": "rule"}


def summarize(data: dict, llm=None) -> dict:
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=900, task="ops_daily_report"))
    try:
        out = music_lyrics._extract_json(llm(_SYSTEM, json.dumps(data, ensure_ascii=False, default=str)[:24000]))
        if not isinstance(out, dict) or out.get("level") not in ("ok", "warn", "error"):
            raise ValueError("형식 오류")
        issues = [{k: str(i.get(k) or "")[:200] for k in ("title", "cause", "suggestion")}
                  for i in (out.get("issues") or []) if isinstance(i, dict)][:5]
        return {"level": out["level"], "headline": str(out.get("headline") or "")[:120], "issues": issues,
                "good": [str(g)[:120] for g in (out.get("good") or [])][:3], "source": "ai"}
    except Exception as e:  # noqa: BLE001
        logger.warning("[ops-report] AI 요약 실패 → 규칙 요약: %s", str(e)[:200])
        return rule_summary(data)


def run(now: datetime | None = None, llm=None) -> dict:
    """수집(+유튜브 성과 갱신) → 요약 → 저장. 반환: 저장한 행."""
    now = now or datetime.now(timezone.utc)
    _safe(lambda: __import__("services.yt_stats", fromlist=["x"]).refresh(now), None)
    data = collect(now)
    summary = apply_credit_issue(summarize(data, llm=llm), data)
    row = {"date": now.astimezone(KST).date().isoformat(), "data": data, "summary": summary,
           "created_at": now.isoformat()}
    _rest(TABLE, "POST", json_body=[row], prefer="resolution=merge-duplicates,return=minimal",
          params={"on_conflict": "date"})
    return row


def latest() -> dict | None:
    rows = _rest(TABLE, params={"select": "date,summary,data,created_at", "order": "date.desc", "limit": "1"})
    if not rows:
        return None
    r = rows[0]
    data = r.get("data") or {}
    return {"date": r.get("date"), "created_at": r.get("created_at"), "summary": r.get("summary") or {},
            "youtube": data.get("youtube") or {}, "channels": data.get("channels") or {}}
