"""쇼츠 시리즈 상태 — 시즌 1 "돌잔치 D-14, 엄마의 2주 챌린지"(15편) 계획·진행을 R2 JSON 으로 관리.

R2 키: shorts/{channel}/series.json (음악 버킷, SQL 없음). 회차마다 형식(A 셀카/B 운동/C 일상)·
등장 인물·엄마 단계(mom/mom_mid/mom_after)·상태·대본·비용·video_id 를 기록한다.

"D-14" 는 **이야기 속 날짜**다(대표 결정) — 업로드는 주 4편이라 실제 날짜와 무관.
엄마 변화 단계(대표 승인): Day 1~6 mom / 7~11 mom_mid(mom 얼굴 + mom_after 전신) / 12~15 mom_after.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone

from adapters import r2_storage

logger = logging.getLogger(__name__)

SEASON = 1
TITLE = "돌잔치 D-14, 엄마의 2주 챌린지"
GOAL = "체력·자신감·돌잔치 원피스"
FORMATS = {"A": "셀카(말 없음·자막)", "B": "운동 동작", "C": "일상 에피소드"}

# (day, format, characters, 내용 메모) — 0단계 초안 + 대표 지시(Day1 엄마 단독, Day4 엄마+아빠, Day6 엄마+아기)
_PLAN: list[tuple[int, str, list[str], str]] = [
    (1, "C", ["mom"], "돌잔치 원피스를 꺼내 보고 챌린지를 결심한다"),
    (2, "B", ["mom"], "거실 스쿼트 첫날 — 힘들지만 끝까지"),
    (3, "A", ["mom"], "근육통 셀카 + 오늘의 다짐"),
    (4, "B", ["dad", "mom"], "아빠 코치 등장 — 과한 열정으로 구령"),
    (5, "C", ["dad", "mom", "baby"], "아빠가 야식으로 방해, 엄마는 버틴다"),
    (6, "B", ["mom", "baby"], "아기가 매트에서 엄마 스트레칭을 따라 한다"),
    (7, "A", ["mom"], "1주 차 — 계단이 덜 힘들어졌다"),
    (8, "B", ["dad", "mom"], "아빠와 플랭크 대결"),
    (9, "C", ["mom", "baby"], "아기 안고 동네 산책 — 숨이 덜 찬다"),
    (10, "B", ["mom"], "스쿼트 횟수가 늘었다(숫자는 횟수만)"),
    (11, "A", ["mom", "baby"], "원피스를 다시 대 본다(결과는 아직 비밀)"),
    (12, "B", ["dad", "mom", "baby"], "가족 홈트 — 셋이 같이 스트레칭"),
    (13, "C", ["dad", "mom"], "아빠의 마지막 방해, 엄마의 승리"),
    (14, "A", ["mom"], "D-1 자신감 셀카"),
    (15, "C", ["dad", "mom", "baby"], "돌잔치 당일 — 가족사진(마지막 편)"),
]


def mom_stage(day: int) -> str:
    if day <= 6:
        return "mom"
    if day <= 11:
        return "mom_mid"
    return "mom_after"


def dday_label(day: int) -> str:
    """Day 1 = D-14 … Day 14 = D-1, Day 15 = D-day(돌잔치)."""
    return "D-day" if day >= 15 else f"D-{15 - day}"


def initial_series(channel: str) -> dict:
    return {
        "channel": channel, "season": SEASON, "title": TITLE, "goal": GOAL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "episodes": [
            {"day": d, "dday": dday_label(d), "format": f, "characters": list(chars),
             "mom_stage": mom_stage(d), "plan": memo, "finale": d == 15,
             "status": "planned", "script": None, "video_id": None, "cost": None,
             "summary": None, "notes": []}
            for d, f, chars, memo in _PLAN
        ],
    }


def _key(channel: str) -> str:
    return f"shorts/{channel}/series.json"


def load(channel: str) -> dict:
    """R2 의 series.json. 없거나 읽기 실패면 초기 계획(저장하지 않음)."""
    if r2_storage.is_available():
        try:
            obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=_key(channel))
            data = json.loads(obj["Body"].read())
            if isinstance(data, dict) and data.get("episodes"):
                return data
        except Exception:  # noqa: BLE001 - 없음 → 초기 계획
            pass
    return initial_series(channel)


def save(channel: str, series: dict) -> None:
    if not r2_storage.is_available():
        raise RuntimeError("R2 미설정 — 시리즈 상태를 저장할 수 없습니다.")
    series["updated_at"] = datetime.now(timezone.utc).isoformat()
    r2_storage._get_client().put_object(
        Bucket=r2_storage._music_bucket(), Key=_key(channel),
        Body=json.dumps(series, ensure_ascii=False).encode(), ContentType="application/json")


def episode(series: dict, day: int) -> dict:
    ep = next((e for e in series["episodes"] if e["day"] == day), None)
    if ep is None:
        raise ValueError(f"시즌 {series.get('season')}에 Day {day} 가 없습니다.")
    return ep


def previous_summaries(series: dict, day: int, n: int = 3) -> list[str]:
    """연속성용 — 직전 회차 요약(제작된 것만, 최근 n개)."""
    prev = [e for e in series["episodes"] if e["day"] < day and e.get("summary")]
    return [f"Day {e['day']}: {e['summary']}" for e in prev[-n:]]


def update_episode(channel: str, day: int, **fields) -> dict:
    """회차 필드 갱신 후 저장. 반환은 갱신된 회차 사본."""
    series = load(channel)
    ep = episode(series, day)
    ep.update(fields)
    save(channel, series)
    return copy.deepcopy(ep)
