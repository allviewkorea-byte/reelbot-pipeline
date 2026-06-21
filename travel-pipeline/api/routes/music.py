"""음악(Rooftop Music) 라우터 — sunoapi.org 콜백 수신(보조).

완료 감지는 폴링이 1차(R2 저장 책임). 이 콜백은 보조 채널이다:
  - callBackUrl 은 suno 요청의 필드라 엔드포인트를 최소로 제공한다.
  - callbackType == complete 일 때만 멱등 R2 저장을 트리거(이미 저장됐으면 skip).
  - theme_slug 는 콜백 본문에 없으므로 callBackUrl 쿼리(?theme_slug=)로 전달받는다.

MUSIC_CALLBACK_BASE_URL 미설정이면 suno 가 콜백을 보내지 않으며, 폴링만으로
정상 동작한다(이 라우트는 호출되지 않을 뿐 문제 없음).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from services import music_suno

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/suno-callback")
async def suno_callback(request: Request, theme_slug: str = ""):
    """suno 생성 콜백. complete 면 멱등 R2 저장을 트리거한다."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - 비정상 본문도 200 으로 흡수(재전송 폭주 방지)
        logger.warning("[music-callback] JSON 파싱 실패")
        return {"ok": False, "error": "invalid json"}

    data = body.get("data") or {}
    cb_type = data.get("callbackType") or body.get("callbackType") or ""
    task_id = data.get("task_id") or data.get("taskId") or ""
    logger.info(
        "[music-callback] type=%s task=%s theme=%s", cb_type, task_id, theme_slug
    )

    if cb_type != "complete":
        # text / first 등 중간 콜백은 로그만(R2 저장은 complete 에서).
        return {"ok": True, "ignored": cb_type}

    # complete 본문의 곡 배열(키 명이 docs/실응답에 따라 다를 수 있어 관대하게 탐색).
    tracks = data.get("data") or data.get("sunoData") or []
    if not isinstance(tracks, list) or not tracks:
        logger.warning("[music-callback] complete 인데 트랙 배열 없음")
        return {"ok": True, "stored": 0}

    try:
        records = music_suno.store_tracks(theme_slug or "untitled", task_id, tracks)
        return {"ok": True, "stored": len(records)}
    except Exception as e:  # noqa: BLE001 - 콜백 실패해도 폴링이 1차라 200 으로 흡수
        logger.warning("[music-callback] 저장 실패: %s", e)
        return {"ok": False, "error": str(e)}
