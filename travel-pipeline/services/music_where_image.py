"""where 채널(rooftop_music) 자동 배경 이미지 — 생성 프롬프트 · 검수 기준(대표 지시 2026-10-16).

기준: 풍경이 아니라 "예술적인 공간 감각". 세계적인 건축가가 설계한 듯한 도심·건물·실내 공간,
여백(빈 공간) 자체가 예술로 느껴지는 절제된 구도. 인물은 가끔(약 30%) 공간의 스케일을 보여주는
작은 뒷모습·실루엣만. 실존 랜드마크를 그대로 그리지 않는다(형태가 틀려 AI 티가 난다) — 노출 콘크리트·
곡면 유리·캔틸레버·빛 우물 같은 "그 수준의 건축 양식"으로만 묘사한다.

★ where 수동 경로 상수(music_image_prompts.IMAGE_PROMPTS·_GEN_SYSTEM·IMAGE_PROMPT_PREFIX 등)는
  참고만 하고 한 글자도 바꾸지 않는다. 이 모듈의 상수는 자동 생성 전용이다.
★ 운동 채널 기준(music_image_prompts.WORKOUT_TONE, music_auto_image._REVIEW_SYSTEM)과도 분리한다.
"""

from __future__ import annotations

import random

# 자동 회차 장르 후보(대표 승인 2026-10-16) — 19장르 중 workout·hiphop·kpop·pop 제외 15개.
WHERE_GENRES: tuple[str, ...] = (
    "citypop", "sunset_drive", "morning_drive", "cafe", "jazz", "ballad", "breakup",
    "sleep_study", "lofi", "rnb_soul", "hotel_lobby", "cafe_bgm", "bar_lounge",
    "spa_meditation", "library_study",
)

PERSON_RATE = 0.30  # 인물 등장 비율 목표

WHERE_TONE = (
    "풍경 사진이 아니라 예술적인 공간 사진. 세계적인 건축가가 설계한 듯한 도심·건물·실내 공간. "
    "여백(넓은 벽면·하늘·바닥) 자체가 예술로 느껴지는 절제된 구도, 빛과 그림자가 만드는 면. "
    "노출 콘크리트·곡면 유리·캔틸레버·빛 우물·석재·원목 같은 건축 언어로 묘사하고, "
    "실존하는 특정 랜드마크·유명 건물은 그대로 그리지 말 것. "
    "직선·기둥은 곧게, 원근은 정확하게(소실점 일관). 녹아내리거나 비틀린 구조물 금지, "
    "과도한 광택·HDR 금지, 자연스러운 필름 같은 색. "
    "화면 중앙은 하얗게 날리지 말 것 — 영상 중앙에 흰 로고가 올라가므로 중앙은 톤과 디테일이 살아 있게. "
    "간판·포스터·벽 글자·로고 등 읽히는 문구 금지."
)

_PERSON_LINE = (
    "공간의 스케일을 보여주는 아주 작은 인물 1명(뒷모습이나 실루엣, 화면의 작은 부분). "
    "얼굴 클로즈업·화보 연출 금지."
)
_NO_PERSON_LINE = "사람 없이 공간만."

# 장르별 공간(대표 예시를 실제 where 장르 목록에 맞춰 확정한 표 — PR 본문 참조).
_SCENES: dict[str, list[str]] = {
    "study": [  # lofi · sleep_study · library_study
        "고요한 노출 콘크리트 도서관, 높은 서가 사이로 오후의 사선 햇빛이 바닥에 긴 면을 그린다.",
        "큰 창가에 놓인 원목 책상 하나, 비스듬한 오후 햇빛과 벽면의 넓은 여백.",
        "빛 우물에서 떨어지는 부드러운 빛이 비어 있는 열람실 바닥을 비춘다.",
        "계단식 독서 공간, 낮은 각도에서 본 콘크리트 단과 창밖의 흐린 하늘.",
    ],
    "drive": [  # citypop · sunset_drive · morning_drive
        "해 질 녘 유리 커튼월 고층 건물, 하늘의 주황빛이 유리면에 반사된다.",
        "비어 있는 고가도로가 도시 위로 곡선을 그리며 이어진다, 해 질 녘 하늘.",
        "네온이 막 켜지기 시작하는 도심 거리, 아직 푸른빛이 남은 저녁 하늘과 매끈한 건물 면.",
        "캔틸레버로 길게 뻗은 건물 아래 텅 빈 도로, 노을빛과 긴 그림자.",
    ],
    "morning": [  # morning_drive 보조
        "이른 아침 햇살이 깨끗한 흰 건물 파사드에 사선 그림자를 만든다, 맑은 하늘.",
        "아침 빛이 드는 곡면 유리 건물 옆으로 비어 있는 넓은 도로.",
        "아침 햇살이 비스듬히 드는 고가도로 아래 넓은 콘크리트 기둥 열, 맑고 차가운 공기.",
        "출근 전 이른 아침, 캔틸레버 지붕 아래 비어 있는 보행 데크와 길게 늘어진 그림자.",
    ],
    "cafe": [  # cafe · cafe_bgm · jazz
        "미니멀한 카페 실내, 원목 테이블과 석재 바, 큰 창 너머로 흐릿한 거리.",
        "높은 천장의 콘크리트 카페, 창가 자리에 드는 오후 빛과 넓은 벽면 여백.",
        "석재와 원목으로 된 작은 카페 코너, 창밖 골목의 부드러운 빛.",
    ],
    "lounge": [  # bar_lounge · hotel_lobby · rnb_soul
        "두 층 높이의 호텔 로비 아트리움, 석재 바닥과 간접 조명, 넓은 여백.",
        "저녁의 바 라운지, 따뜻한 간접 조명이 석재 벽과 원목 카운터를 부드럽게 비춘다.",
        "곡면 벽을 따라 흐르는 은은한 빛, 비어 있는 라운지 소파와 넓은 바닥.",
    ],
    "calm": [  # spa_meditation
        "새벽빛이 드는 텅 빈 갤러리, 하얀 벽과 바닥에 떨어진 빛의 사각형.",
        "물이 고인 중정, 수면에 비친 콘크리트 벽과 하늘.",
        "안개 낀 정원 속 낮은 건축물, 부드러운 새벽빛과 고요한 여백.",
    ],
    "rain": [  # breakup · ballad
        "비에 젖은 광장과 캐노피, 반사되는 바닥에 건물 불빛이 번진다.",
        "비 오는 저녁, 유리 캐노피 아래 비어 있는 보행로와 젖은 석재 바닥의 반사.",
        "빗방울이 맺힌 큰 창 너머 흐린 도심, 실내는 어둡지 않고 차분한 톤.",
    ],
}

_GENRE_GROUP: dict[str, list[str]] = {
    "lofi": ["study"], "sleep_study": ["study", "calm"], "library_study": ["study"],
    "citypop": ["drive"], "sunset_drive": ["drive"], "morning_drive": ["morning"],
    "cafe": ["cafe"], "cafe_bgm": ["cafe"], "jazz": ["cafe", "lounge"],
    "bar_lounge": ["lounge"], "hotel_lobby": ["lounge"], "rnb_soul": ["lounge"],
    "spa_meditation": ["calm"], "breakup": ["rain"], "ballad": ["rain"],
}


def scene_pool(genre: str | None) -> list[str]:
    """장르 → 공간 장면 풀. 미등록 장르는 도심 드라이브 풀(where 기본 결)."""
    out: list[str] = []
    for grp in _GENRE_GROUP.get((genre or "").strip(), ["drive"]):
        out.extend(_SCENES[grp])
    return out


def build_prompt(genre: str | None, avoid: list[str] | None = None, *, rng: random.Random | None = None) -> str:
    """where 자동 배경 최종 프롬프트. avoid: 앞 시도의 검수 불합격 사유(다음 시도에 덧붙임)."""
    r = rng or random
    scene = r.choice(scene_pool(genre))
    person = _PERSON_LINE if r.random() < PERSON_RATE else _NO_PERSON_LINE
    prompt = (
        "실제 건축 사진작가가 고급 카메라로 촬영한 가로 16:9 비율 사진. 고해상도, 선명하고 디테일이 풍부하게. "
        "AI가 만든 느낌 절대 없이. 텍스트, 글자, 워터마크 없이. "
        f"{WHERE_TONE} {scene} {person}"
    )
    if avoid:
        prompt += " 이번엔 반드시 피할 것(직전 시도 검수 불합격 사유): " + "; ".join(avoid) + "."
    return prompt


REVIEW_SYSTEM = (
    "너는 감성 음악 플레이리스트 유튜브 채널(where;)의 배경 이미지 검수자다. 이 이미지는 영상 전체 배경과 "
    "썸네일로 그대로 쓰이고, 화면 중앙에 흰 로고가 올라간다.\n"
    "합격 기준: 세계적인 건축가가 설계한 듯한 도심·건물·실내 공간을 담은 예술적인 공간 사진. "
    "여백(벽면·하늘·바닥)과 빛·그림자의 면이 살아 있는 절제된 구도. 인물은 없거나, 공간의 스케일을 "
    "보여주는 작은 뒷모습·실루엣이면 정상이다.\n"
    "아래 불합격 기준 중 하나라도 해당하면 불합격이다.\n"
    "1. 간판·포스터·벽 글자·큰 글자·로고·워터마크가 보인다.\n"
    "2. 실존하는 유명 랜드마크·특정 건물로 바로 알아볼 수 있다.\n"
    "3. AI 티: 휘거나 비틀린 직선·기둥, 맞지 않는 원근, 녹아내린 구조물, 손·관절 왜곡, 과도한 광택·HDR.\n"
    "4. 얼굴 정면 클로즈업이나 화보처럼 인물이 주인공인 사진.\n"
    "5. 건축·공간이 아닌 자연 풍경 위주(산·바다·숲만 있는 사진).\n"
    "6. 화면 중앙이 하얗게 날아가 있다 — 중앙의 흰 로고가 안 보일 정도로 중앙이 희거나 과노출이면 불합격.\n"
    "7. 너무 어둡거나 탁해서 공간이 잘 보이지 않는다.\n"
    "애매하면 불합격으로 판단한다.\n"
    '반드시 JSON 한 개만 출력한다: {"pass": true 또는 false, "reasons": ["불합격 사유(한국어, 짧게)"]}. '
    "합격이면 reasons 는 빈 배열."
)
