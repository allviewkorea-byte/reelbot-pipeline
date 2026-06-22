"""sunoapi.org 음악 생성 어댑터 (Rooftop Music).

테마 파라미터로 음악을 생성(요청당 2곡) → 폴링(또는 콜백)으로 완료 감지 →
mp3 를 즉시 R2 에 영구 저장 → Supabase `music_tracks` 에 기록한다.

⚠️ sunoapi 의 mp3 는 15일 후 삭제되므로 SUCCESS 직후 반드시 R2 로 복사한다
(R2 저장 완료 전 다음 단계로 넘어가지 않는다). 저장은 r2_key head_object 로
멱등 — 폴링과 콜백이 같은 곡을 동시에 처리해도 1회만 업로드/기록한다.

완료 감지 정책(합의): **폴링이 1차(R2 저장 책임)**, 콜백은 보조(로그 + 멱등 트리거).

API (https://docs.sunoapi.org):
  - 생성: POST {BASE}/generate            body=customMode/instrumental/model/style/title/...
          → data.taskId (요청당 2곡 생성)
  - 폴링: GET  {BASE}/generate/record-info?taskId=
          status PENDING / TEXT_SUCCESS / FIRST_SUCCESS / SUCCESS / *_FAILED
          SUCCESS → response.sunoData[] (id, audioUrl, duration, title, tags)
  - 인증: Authorization: Bearer <SUNOAPI_ORG_KEY>

환경변수:
  SUNOAPI_ORG_KEY          — API 키(필수)
  MUSIC_CALLBACK_BASE_URL  — Railway 공개 URL(선택). 있으면 callBackUrl 자동 구성,
                             없으면 콜백 생략(폴링만으로 정상 동작).
  R2_MUSIC_BUCKET / R2_MUSIC_PUBLIC_BASE_URL — 음악 마스터 전용 버킷(권장, r2_storage).
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from urllib.parse import quote

import httpx

from adapters import r2_storage
from services import music_store

logger = logging.getLogger(__name__)

SUNO_BASE = "https://api.sunoapi.org/api/v1"

# 폴링 기본값 — suno 생성은 보통 2~3분. #30: 600→900(15분)으로 늘려 타임아웃으로
# 과금만 되고 버려지는 곡을 방지(콜백 도착 시엔 폴링 안 기다리고 즉시 진행).
POLL_INTERVAL = 15
POLL_TIMEOUT = 900

# 종료 상태(이 외에는 진행 중으로 보고 계속 폴링).
_SUCCESS = "SUCCESS"


def is_available() -> bool:
    return bool(os.getenv("SUNOAPI_ORG_KEY"))


def _headers() -> dict:
    key = (os.getenv("SUNOAPI_ORG_KEY") or "").strip()
    if not key:
        raise RuntimeError("SUNOAPI_ORG_KEY 미설정")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _public_base() -> str:
    """suno 가 콜백을 보낼 수 있는 **외부 공개** 베이스 URL.

    우선순위: MUSIC_CALLBACK_BASE_URL > BACKEND_PUBLIC_URL > RAILWAY_PUBLIC_DOMAIN(자동).
    #30: '*.railway.internal'(Railway 내부 도메인)은 외부 suno 서버가 접근 불가 →
    무시하고 다음 후보로 넘어간다(잘못 설정돼도 자동 복구).
    """
    for var in ("MUSIC_CALLBACK_BASE_URL", "BACKEND_PUBLIC_URL"):
        v = (os.getenv(var) or "").strip().rstrip("/")
        if v and "railway.internal" not in v:
            return v
    dom = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip().rstrip("/")
    if dom and "railway.internal" not in dom:
        return dom if dom.startswith("http") else f"https://{dom}"
    return ""


def callback_url(theme_slug: str = "") -> str:
    """외부 공개 베이스가 있으면 콜백 URL 을 구성(theme_slug 쿼리 포함).

    콜백은 theme_slug 를 모르므로 callBackUrl 쿼리에 실어 R2 키를 구성하게 한다.
    미설정/내부도메인뿐이면 빈 문자열(→ callBackUrl 생략, 폴링만으로 동작).
    """
    base = _public_base()
    if not base:
        return ""
    q = f"?theme_slug={quote(theme_slug)}" if theme_slug else ""
    return f"{base}/api/music/suno-callback{q}"


def _build_body(theme: dict) -> dict:
    """테마 dict → 생성 요청 body. 누락 시 안전한 기본값.

    instrumental=True(기본): 연주곡 — 기존 동작 그대로(회귀 없음).
    instrumental=False: 보컬곡 — body 에 prompt=가사를 넣는다(sunoapi customMode
      보컬은 prompt 가 가사). 가사가 없으면 ValueError(보컬인데 가사 누락 방지).
    기본 모델: 보컬 V5_5 / 연주 V5.
    """
    instrumental = bool(theme.get("instrumental", True))
    default_model = "V5" if instrumental else "V5_5"
    body: dict = {
        "customMode": theme.get("customMode", True),
        "instrumental": instrumental,
        "model": theme.get("model") or default_model,
        "style": theme.get("style", ""),
        "title": theme.get("title", ""),
    }
    # 보컬곡: prompt(가사) 필수. lyrics(우선) 또는 prompt 필드를 받는다.
    if not instrumental:
        lyrics = (theme.get("lyrics") or theme.get("prompt") or "").strip()
        if not lyrics:
            raise ValueError(
                "보컬곡(instrumental=false)에는 가사가 필요합니다 — theme['lyrics'] 또는 theme['prompt'] 를 채워주세요."
            )
        body["prompt"] = lyrics
    # 선택 파라미터 — 값이 있을 때만 포함.
    for opt in ("negativeTags", "vocalGender", "styleWeight", "weirdnessConstraint"):
        if theme.get(opt) is not None:
            body[opt] = theme[opt]
    cb = callback_url(theme.get("theme_slug", ""))
    if cb:
        body["callBackUrl"] = cb
    else:
        logger.warning(
            "[suno] MUSIC_CALLBACK_BASE_URL 미설정 — callBackUrl 생략(폴링만 사용)"
        )
    return body


def submit_generation(theme: dict) -> str:
    """생성 요청 → taskId 반환(요청당 2곡 생성됨)."""
    body = _build_body(theme)
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{SUNO_BASE}/generate", headers=_headers(), json=body)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error("[suno] generate 오류: %s - %s", r.status_code, r.text[:300])
            raise
        data = r.json()
    # sunoapi.org 응답 봉투: {code, msg, data:{taskId}}
    code = data.get("code")
    if code not in (200, "200", None):
        raise RuntimeError(f"suno generate 실패: code={code} msg={data.get('msg')}")
    task_id = (data.get("data") or {}).get("taskId")
    if not task_id:
        raise RuntimeError(f"suno generate 응답에 taskId 없음: {str(data)[:300]}")
    logger.info("[suno] 생성 요청 OK taskId=%s", task_id)
    return task_id


def _norm_track(item: dict) -> dict:
    """record-info(sunoData) / 콜백(data) 키 차이를 흡수(audioUrl vs audio_url 등)."""
    return {
        "audio_id": item.get("id") or item.get("audio_id") or "",
        "audio_url": item.get("audioUrl") or item.get("audio_url") or "",
        "title": item.get("title") or "",
        "tags": item.get("tags") or "",
        "duration": item.get("duration"),
    }


def poll_task(
    task_id: str,
    *,
    timeout: int = POLL_TIMEOUT,
    interval: int = POLL_INTERVAL,
) -> list[dict]:
    """SUCCESS 까지 record-info 를 폴링하고 정규화된 트랙 리스트를 반환.

    *_FAILED → RuntimeError, timeout 초과 → TimeoutError.
    """
    elapsed = 0
    with httpx.Client(timeout=60.0) as c:
        while elapsed < timeout:
            time.sleep(interval)
            elapsed += interval
            r = c.get(
                f"{SUNO_BASE}/generate/record-info",
                headers=_headers(),
                params={"taskId": task_id},
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError:
                logger.error(
                    "[suno] record-info 오류: %s - %s", r.status_code, r.text[:300]
                )
                raise
            data = r.json().get("data") or {}
            status = data.get("status") or ""
            if status == _SUCCESS:
                suno_data = (data.get("response") or {}).get("sunoData") or []
                tracks = [_norm_track(it) for it in suno_data]
                logger.info("[suno] %s SUCCESS — 곡 %d개", task_id, len(tracks))
                return tracks
            if status.endswith("FAILED"):
                msg = data.get("errorMessage") or data.get("msg") or status
                raise RuntimeError(f"suno 생성 실패({status}): {msg}")
            logger.info("[suno] %s 상태=%s (%ds)", task_id, status or "?", elapsed)
    raise TimeoutError(f"suno 폴링 타임아웃({timeout}s 초과) taskId={task_id}")


def _download_mp3(url: str, dest: str) -> str:
    """mp3 를 dest 로 스트리밍 다운로드."""
    with httpx.Client(timeout=180.0, follow_redirects=True) as c:
        with c.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1024 * 64):
                    f.write(chunk)
    return dest


def store_tracks(theme_slug: str, task_id: str, tracks: list[dict]) -> list[dict]:
    """완료된 곡들을 R2 영구 저장 + DB 기록(멱등). 저장된 record 리스트 반환.

    폴링·콜백 양쪽에서 호출 가능 — r2_storage.music_exists 로 중복 업로드를 막고,
    DB 는 id(=audio_id) upsert 로 1행만 남긴다. R2 저장 완료 전에는 DB 를 건드리지
    않는다(15일 삭제 대비 — R2 가 진실의 출처).
    """
    records: list[dict] = []
    for t in tracks:
        nt = _norm_track(t) if "audio_id" not in t else t
        audio_id = nt.get("audio_id") or ""
        audio_url = nt.get("audio_url") or ""
        if not audio_id or not audio_url:
            logger.warning("[suno] 트랙 누락(id/url) — 건너뜀: %s", str(nt)[:200])
            continue

        r2_key = r2_storage.music_key(theme_slug, audio_id)
        # ── R2 즉시 저장(핵심) — 이미 있으면 재업로드 생략(멱등) ──
        if r2_storage.music_exists(theme_slug, audio_id):
            logger.info("[suno] R2 이미 존재 — 업로드 생략 key=%s", r2_key)
        elif not r2_storage.is_available():
            logger.warning("[suno] R2 미설정 — 영구 저장 불가(⚠️ 15일 후 삭제 위험)")
        else:
            # Windows 파일 잠금 회피: 핸들을 닫은 뒤 같은 경로로 재오픈(다운로드/업로드).
            fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            try:
                _download_mp3(audio_url, tmp_path)
                r2_storage.upload_music(tmp_path, theme_slug, audio_id)
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.info("[suno] R2 저장 OK key=%s", r2_key)

        record = {
            "id": audio_id,
            "theme_slug": theme_slug,
            "task_id": task_id,
            "audio_id": audio_id,
            "title": nt.get("title") or "",
            "tags": nt.get("tags") or "",
            "duration": nt.get("duration"),
            "r2_key": r2_key,
            "status": "SUCCESS",
        }
        music_store.upsert_track(record)
        records.append(record)
    return records


def generate_and_store(
    theme: dict,
    *,
    timeout: int = POLL_TIMEOUT,
    interval: int = POLL_INTERVAL,
) -> dict:
    """생성 → 폴링(SUCCESS) → R2 저장 + DB 기록을 한 번에. 검증/운영 진입점.

    theme: {theme_slug, instrumental, model, style, title, negativeTags?, ...}
    Returns: {task_id, tracks:[record...]}
    """
    theme_slug = theme.get("theme_slug") or "untitled"
    task_id = submit_generation(theme)
    tracks = poll_task(task_id, timeout=timeout, interval=interval)
    records = store_tracks(theme_slug, task_id, tracks)
    return {"task_id": task_id, "tracks": records}
