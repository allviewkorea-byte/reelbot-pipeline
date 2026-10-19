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

import os
import random
from datetime import datetime, timedelta, timezone

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


# ══ 두 번째 스타일: 유럽 거리 필름 스냅(대표 결정 2026-10-19) ═══════════════════════════
# 위 건축 공간 스타일(상수·함수·검수)은 한 글자도 바꾸지 않고 **추가만** 한다.
# 회차마다 허용 장르면 MUSIC_WHERE_STREET_RATE(기본 0.4) 확률로 거리 스냅, 아니면 건축 공간.
STYLE_SPACE = "space"    # 기존 건축 공간(#341)
STYLE_STREET = "street"  # 유럽 거리 필름 스냅

# 거리 스냅 허용 장르(0단계 승인) — bar_lounge 는 실내 장소 BGM 결이라 제외.
STREET_GENRES: frozenset[str] = frozenset({
    "jazz", "cafe", "ballad", "breakup", "morning_drive", "citypop",
    "sunset_drive", "rnb_soul", "cafe_bgm",
})


def street_rate() -> float:
    try:
        v = float((os.getenv("MUSIC_WHERE_STREET_RATE") or "").strip() or 0.4)
    except ValueError:
        v = 0.4
    return max(0.0, min(1.0, v))


def pick_style(genre: str | None, *, rng: random.Random | None = None) -> str:
    """회차 배경 스타일. 허용 장르만 street_rate 확률로 거리 스냅, 나머지는 항상 건축 공간."""
    r = rng or random
    if (genre or "").strip() in STREET_GENRES and r.random() < street_rate():
        return STYLE_STREET
    return STYLE_SPACE


STREET_TONE = (
    "유럽 구시가지 거리 — 오래된 석조 건물·나무 대문·철제 창살·돌바닥 골목·붉은 벽돌 건물·노천카페·가로수. "
    "실존하는 특정 랜드마크·유명 건물은 그대로 그리지 말 것. "
    "따뜻한 35mm 필름 톤, 은은한 입자감, 붉은/버건디 포인트 한 가지(가방·머플러·니트 등). "
    "과도한 광택·HDR 금지, 자연스러운 필름 색. "
    "간판·명판·표지판·포스터 글자·브랜드 로고 등 읽히는 문구 금지. "
    "참고 사진을 복제하지 말고 그런 결로 새로운 장면을 만들 것."
)

STREET_PERSON_LINE = (
    "인물은 1명(배경 행인은 아주 작게만). 전신 또는 무릎 위 중거리, 앉거나 걷는 자연스러운 캔디드 순간. "
    "얼굴은 옆모습·뒷모습·선글라스·고개 숙임 — 얼굴 정면 클로즈업 금지. "
    "단정하고 클래식한 옷차림 — 옷은 계절 문구를 따르고(롱스커트·작은 가방 등), 노출이 과한 옷·브랜드 로고 금지. "
    "인물은 화면 오른쪽 끝 1/3(가로 70~90% 지점)에 두고 머리 위로 여백을 남길 것. "
    "화면 중앙과 왼쪽 아래는 비워 두고 중앙은 하얗게 날리지 말 것 — 중앙에 흰 로고, 왼쪽 아래에 곡 제목이 올라간다."
)

# KST 현재 월 → 계절 문구(인물 옷·가로수·빛은 계절이 정한다. 장면은 계절 중립).
SEASON_LINES: dict[str, str] = {
    "spring": "봄. 연둣빛 새잎 가로수와 화분의 꽃, 가벼운 가디건·셔츠·롱스커트·로퍼, 맑고 부드러운 햇살.",
    "summer": "여름. 짙은 초록 가로수, 리넨 셔츠·민소매 아닌 반팔 블라우스·롱스커트·샌들, 선명한 햇살과 그늘(노출 과한 옷 금지).",
    "autumn": "가을. 단풍 든 가로수와 바닥의 낙엽, 니트·머플러·트렌치코트·롱스커트·부츠, 낮은 황금빛.",
    "winter": "겨울. 앙상한 가로수, 울 코트·목도리·장갑·부츠, 차가운 공기, 가끔 얇게 쌓인 눈.",
}
_KST = timezone(timedelta(hours=9))


def season_of(month: int) -> str:
    """3~5 봄 / 6~8 여름 / 9~11 가을 / 12~2 겨울."""
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"


def current_season(now: datetime | None = None) -> str:
    return season_of((now or datetime.now(_KST)).astimezone(_KST).month)


# 장르 결별 거리 스냅 장면(0단계 승인 초안 그대로, 계절 중립).
_STREET_SCENES: dict[str, list[str]] = {
    "jazz": [  # 저녁·골목
        "해가 진 직후 골목 끝 노천카페, 작은 테이블에 혼자 앉아 커피잔을 든 여성, 창살 너머 따뜻한 전구빛.",
        "오래된 석조 아치 아래 돌계단에 앉아 고개를 숙인 여성, 옆에 둔 작은 가방.",
        "저녁 비가 그친 돌바닥 골목을 천천히 걸어가는 뒷모습, 젖은 바닥에 번지는 가로등빛.",
        "철제 발코니가 이어진 좁은 거리, 문간에 기대 선 측면 전신.",
        "지하 재즈 바 입구 계단 옆(간판 없음)에 서서 옆을 보는 여성.",
        "광장 모서리 낮은 벽에 앉아 책을 덮은 여성, 멀리 작은 행인들.",
        "붉은 문의 오래된 가게 앞(글자 없음)을 지나가는 측면 걸음.",
    ],
    "cafe": [  # 낮·노천카페 — cafe · cafe_bgm
        "오후 햇살 드는 노천카페 테라스, 창가 쪽 의자에 앉아 창밖을 보는 옆모습.",
        "나무 대문 옆 작은 카페 테이블, 크루아상 접시와 책, 선글라스를 쓴 여성.",
        "돌바닥 골목 카페 앞 화분 사이를 걸어 지나가는 측면 전신.",
        "차양 아래 2인 테이블에 혼자 앉아 컵을 감싼 손, 무릎 위 구도.",
        "넝쿨이 덮인 석조 벽 앞 노천 자리, 고개를 숙여 노트를 쓰는 여성.",
        "모퉁이 카페 창 앞 벤치에 앉아 다리를 꼰 여성, 창에는 반사만 있고 글자 없음.",
    ],
    "rain": [  # 비 온 뒤·뒷모습·여운 — ballad · breakup
        "비 온 뒤 젖은 돌바닥 거리를 우산을 접고 걸어가는 뒷모습.",
        "오래된 석조 건물 나무 대문 앞 돌계단에 혼자 앉아 무릎을 끌어안은 여성.",
        "흐린 오후 강변 돌난간에 기대 먼 곳을 보는 측면.",
        "가로수 길 끝으로 멀어지는 작은 뒷모습, 바닥의 낙엽과 물웅덩이.",
        "창살 있는 1층 창 아래 벤치에 앉아 편지를 접는 손, 고개 숙임.",
        "텅 빈 아침 광장을 가로지르는 한 사람, 긴 그림자.",
        "붉은 벽돌 건물 모퉁이에 서서 뒤돌아보는 옆모습.",
    ],
    "morning": [  # 아침·빵집·출발 — morning_drive
        "이른 아침 빵집 앞(간판 없음), 종이봉투를 안고 나오는 여성.",
        "아침 햇살 드는 돌바닥 골목을 자전거를 끌고 걷는 측면.",
        "막 문을 연 꽃가게 앞 양동이 꽃 사이를 지나가는 걸음.",
        "아침 빛이 비스듬히 드는 석조 계단을 내려가는 전신.",
        "정류장 벤치(글자 없음)에 앉아 커피를 든 채 길을 보는 옆모습.",
        "덧창을 연 아파트 줄지은 거리를 가방을 메고 걸어가는 뒷모습.",
    ],
    "sunset": [  # 해 질 녘·도시 산책 — citypop · sunset_drive
        "해 질 녘 붉은 벽돌 거리, 가로수 아래를 걸어가는 측면 전신, 주황 빛.",
        "오래된 돌다리 위 난간에 기대 노을을 보는 뒷모습.",
        "언덕길 계단 위에서 내려다보는 지붕들과 그 끝에 앉은 여성.",
        "노을빛이 반사되는 상점 쇼윈도(글자 없음) 앞을 지나가는 걸음.",
        "저녁 골목 노천 테이블에서 일어서는 순간, 손에 든 작은 가방.",
        "강변 산책로 벤치에 앉아 이어폰을 낀 옆모습, 물에 번지는 빛.",
    ],
    "soul": [  # 저녁·따뜻한 조명 — rnb_soul
        "따뜻한 전구가 걸린 저녁 골목 계단에 앉은 여성, 고개를 살짝 돌린 옆모습.",
        "붉은 벽돌 벽에 기대 선 무릎 위 구도, 손에 든 작은 가방.",
        "창마다 불이 켜진 좁은 거리를 걸어가는 뒷모습.",
        "문이 열린 오래된 가게(글자 없음) 불빛 앞에 선 측면 실루엣.",
        "비 그친 밤 돌바닥의 반사광 속을 천천히 걷는 전신.",
        "아치형 통로 끝 빛을 향해 걸어가는 뒷모습.",
    ],
}

_STREET_GENRE_GROUP: dict[str, str] = {
    "jazz": "jazz", "cafe": "cafe", "cafe_bgm": "cafe", "ballad": "rain", "breakup": "rain",
    "morning_drive": "morning", "citypop": "sunset", "sunset_drive": "sunset", "rnb_soul": "soul",
}


def street_scene_pool(genre: str | None) -> list[str]:
    """장르 → 거리 스냅 장면 풀. 미등록 장르는 해 질 녘 산책 풀."""
    return list(_STREET_SCENES[_STREET_GENRE_GROUP.get((genre or "").strip(), "sunset")])


def build_street_prompt(
    genre: str | None, avoid: list[str] | None = None, *,
    rng: random.Random | None = None, now: datetime | None = None,
) -> str:
    """거리 스냅 최종 프롬프트(장르 장면 + KST 계절 + 인물·구도 규칙). avoid: 직전 시도 불합격 사유."""
    r = rng or random
    scene = r.choice(street_scene_pool(genre))
    season = SEASON_LINES[current_season(now)]
    prompt = (
        "실제 사진작가가 35mm 필름 카메라로 찍은 가로 16:9 비율 스트리트 스냅 사진. 고해상도, 선명하고 디테일이 풍부하게. "
        "AI가 만든 느낌 절대 없이. 텍스트, 글자, 워터마크 없이. "
        f"{STREET_TONE} 장면: {scene} 계절: {season} {STREET_PERSON_LINE}"
    )
    if avoid:
        prompt += " 이번엔 반드시 피할 것(직전 시도 검수 불합격 사유): " + "; ".join(avoid) + "."
    return prompt


STREET_REVIEW_SYSTEM = (
    "너는 감성 음악 플레이리스트 유튜브 채널(where;)의 배경 이미지 검수자다. 이 이미지는 영상 전체 배경과 "
    "썸네일로 그대로 쓰이고, 화면 중앙에 흰 로고가, 왼쪽 아래에 곡 제목이 올라간다.\n"
    "합격 기준: 유럽 구시가지 거리(석조 건물·나무 대문·돌바닥 골목·붉은 벽돌·노천카페·가로수)에서 찍은 "
    "따뜻한 35mm 필름 톤 스냅. 인물 1명이 주인공이어도 된다 — 전신 또는 무릎 위 중거리, 앉거나 걷는 "
    "자연스러운 순간.\n"
    "아래 불합격 기준 중 하나라도 해당하면 불합격이다.\n"
    "1. 간판·명판·표지판·포스터 문구·큰 글자·로고·워터마크·옷의 브랜드 로고가 보인다.\n"
    "2. 실존하는 유명 랜드마크·특정 건물로 바로 알아볼 수 있다.\n"
    "3. AI 티: 손가락·손발·관절 왜곡, 얼굴 뭉개짐, 휘거나 비틀린 직선·창틀, 맞지 않는 원근, "
    "녹아내린 구조물, 과도한 광택·HDR.\n"
    "4. 얼굴 정면 클로즈업(얼굴이 화면을 크게 차지하거나 카메라를 정면으로 응시).\n"
    "5. 노출이 과한 옷(수영복·속옷 수준, 크롭·초미니 등).\n"
    "6. 인물이 화면 가로 가운데(로고 자리)에 있다.\n"
    "7. 화면 중앙이 하얗게 날아가 있다 — 중앙의 흰 로고가 안 보일 정도로 중앙이 희거나 과노출이면 불합격.\n"
    "8. 너무 어둡거나 탁해서 장면이 잘 보이지 않는다.\n"
    "애매하면 불합격으로 판단한다.\n"
    '반드시 JSON 한 개만 출력한다: {"pass": true 또는 false, "reasons": ["불합격 사유(한국어, 짧게)"]}. '
    "합격이면 reasons 는 빈 배열."
)
