"""인스타 쇼핑 — 착장 장면 기획 + 프롬프트 (A1). 순수 로직(외부 호출은 plan_scene 의 Claude 1회뿐).

흐름: 요일 → 생활 → 장소 후보 / 포즈 풀(17) / 확정 헤어 / 아이웨어(7종 × 4방식).
1) 규칙으로 후보를 먼저 거른다(결정적·테스트 가능):
   - 신발이 보이는 포즈는 방(room) 금지. 양말 포즈는 방에서만. 거울 포즈는 거울 있는 장소에서만.
   - 신발 상품이 있으면 방 장소는 후보에서 뺀다(대안이 하나도 없을 때만 허용).
   - 최근 2번 연속 같은 헤어·포즈·장소면 그 값은 제외(3연속 금지). 현관 거울은 최근 7일 2회까지.
   - 아이웨어: 직전 2번 모두 없음 → 이번엔 씀 / 직전에 씀 → 안 씀 / 그 외 30% (3번 중 1번 정도),
     같은 아이템 연속 금지.
2) Claude 가 유효한 (장소, 포즈) 조합과 헤어 중에서 고르고 이유를 한 줄 남긴다(JSON). 응답이 목록 밖이거나
   호출이 실패하면 후보 중 무작위로 고른다(기획이 생성을 막지 않게).
3) 프롬프트는 대표 실측 골격 그대로. 참조 순서 ① 01_face ② 02_body ③ hair ④~ 상품(합계 최대 10).
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
MAX_REFS = 10

# ── 장소 ─────────────────────────────────────────────────────────────────
# kind: room(집 안 방·거실 — 신발 금지) / entry(현관 타일) / elevator / fitting / indoor(공공 실내) / outdoor
LOCATIONS: dict[str, dict] = {
    "entry_mirror": {"ko": "현관 거울", "kind": "entry", "mirror": True,
                     "en": "standing on the entryway tile floor by the shoe cabinet of a Korean apartment, in front of a full-length mirror"},
    # 스튜디오 룩북(2026-10-28 실험, 레퍼런스 @yproject.ai) — 요일 장소 목록엔 없음: 지정할 때만 쓰인다
    "white_studio": {"ko": "흰 스튜디오", "kind": "studio", "mirror": False,
                     "en": "in a clean bright photo studio with a seamless warm-white backdrop and floor"},
    "elevator_mirror": {"ko": "엘리베이터 거울", "kind": "elevator", "mirror": True,
                        "en": "inside a Korean apartment elevator with a mirrored wall"},
    "office_lobby": {"ko": "오피스 로비", "kind": "indoor", "mirror": False, "en": "in a bright modern office building lobby"},
    "subway_stairs": {"ko": "지하철 출구 계단", "kind": "outdoor", "mirror": False, "stairs": True,
                      "en": "at a Seoul subway station exit staircase"},
    "evening_alley": {"ko": "저녁 골목", "kind": "outdoor", "mirror": False,
                      "en": "in a quiet Seoul back alley in the early evening with warm shop lights"},
    "restaurant_front": {"ko": "레스토랑 앞", "kind": "outdoor", "mirror": False,
                         "en": "in front of a small restaurant entrance in Seoul at dusk"},
    "fitting_room": {"ko": "백화점 피팅룸", "kind": "fitting", "mirror": True,
                     "en": "inside a department store fitting room with a large mirror"},
    "street": {"ko": "거리", "kind": "outdoor", "mirror": False, "en": "on a busy Seoul shopping street"},
    "crosswalk": {"ko": "횡단보도", "kind": "outdoor", "mirror": False, "en": "on a Seoul crosswalk"},
    "rooftop": {"ko": "루프탑", "kind": "outdoor", "mirror": False, "railing": True,
                "en": "on a city rooftop terrace with the skyline behind"},
    "bar_front": {"ko": "바 앞", "kind": "outdoor", "mirror": False, "en": "in front of a cozy bar entrance at night"},
    "cafe": {"ko": "카페", "kind": "indoor", "mirror": False, "en": "inside a bright minimal cafe"},
    "gallery_stairs": {"ko": "전시장 계단", "kind": "indoor", "mirror": False, "stairs": True, "railing": True,
                       "en": "on the concrete stairs of an art gallery"},
    "park_bench": {"ko": "공원 벤치", "kind": "outdoor", "mirror": False, "en": "in a city park by a wooden bench"},
    "room": {"ko": "방", "kind": "room", "mirror": True,
             "en": "in her bright bedroom with a full-length floor mirror"},
    "neighborhood_alley": {"ko": "동네 골목", "kind": "outdoor", "mirror": False, "en": "in a quiet residential alley in Seoul"},
    "bakery_front": {"ko": "빵집 앞", "kind": "outdoor", "mirror": False, "en": "in front of a neighborhood bakery"},
    # 장소 확장(대표 2026-10-27 "산·바다·학교 근처·교실·차 안 등 다양하게") — 학교는 성인 대학 캠퍼스로만
    "han_river": {"ko": "한강 공원", "kind": "outdoor", "mirror": False,
                  "en": "at a Han River park in Seoul with the river and bridges behind"},
    "campus": {"ko": "대학 캠퍼스", "kind": "outdoor", "mirror": False,
               "en": "on a Seoul university campus with red-brick buildings and trees"},
    "lecture_hall": {"ko": "대학 강의실", "kind": "indoor", "mirror": False,
                     "en": "in a university lecture hall with rows of desks, a few students' bags around, adult college setting"},
    "library": {"ko": "도서관·스터디카페", "kind": "indoor", "mirror": False,
                "en": "at a quiet library or study cafe desk with books and a laptop"},
    "bookstore": {"ko": "서점", "kind": "indoor", "mirror": False, "en": "between the shelves of a cozy bookstore"},
    "subway_car": {"ko": "지하철 안", "kind": "indoor", "mirror": False,
                   "en": "inside a Seoul subway car, standing by the doors"},
    "seongsu_street": {"ko": "성수동 골목", "kind": "outdoor", "mirror": False,
                       "en": "on a trendy Seongsu-dong street with red-brick cafes and pop-up stores"},
    "convenience_store": {"ko": "편의점 앞", "kind": "outdoor", "mirror": False,
                          "en": "in front of a Korean convenience store at night, plastic tables outside"},
    "amusement_park": {"ko": "놀이공원", "kind": "outdoor", "mirror": False,
                       "en": "at an amusement park with rides and colorful lights behind"},
    "car": {"ko": "차 안 조수석", "kind": "vehicle", "mirror": False,
            "en": "in the passenger seat of a car, seatbelt on, daylight through the windows"},
    "train_window": {"ko": "기차 창가 자리", "kind": "vehicle", "mirror": False,
                     "en": "in a window seat on a KTX train, scenery passing outside"},
    "airport": {"ko": "공항", "kind": "indoor", "mirror": False,
                "en": "in a bright airport departure hall with a small suitcase"},
    "beach": {"ko": "바닷가", "kind": "outdoor", "mirror": False,
              "en": "on a Korean east-coast beach with waves and wide sky"},
    "mountain_view": {"ko": "산 전망대", "kind": "outdoor", "mirror": False, "seasons": ["spring", "summer", "autumn"],
                      "en": "at a mountain trail viewpoint overlooking the city"},
    "autumn_foliage": {"ko": "단풍길", "kind": "outdoor", "mirror": False, "seasons": ["autumn"],
                       "en": "on a path lined with red and yellow autumn leaves"},
    # 한국다운 거리 감성(대표 레퍼런스 2026-10-27: 셔터 내려간 상가에 등 기대고 앞을 보는 컷)
    "shutter_street": {"ko": "셔터 내린 상가 골목", "kind": "outdoor", "mirror": False,
                       "en": "on a Seoul shopping street with closed colorful metal roller shutters, vertical Korean shop "
                             "signs and neon in the background, a few blurred passers-by"},
    "euljiro_alley": {"ko": "을지로 노포 골목", "kind": "outdoor", "mirror": False,
                      "en": "in an old Euljiro alley with retro printing shops, plastic stools and dim warm lights"},
    "market_alley": {"ko": "시장 골목", "kind": "outdoor", "mirror": False,
                     "en": "in a lively traditional Korean market alley with stalls and hanging lights"},
    "snowy_street": {"ko": "눈 내린 거리", "kind": "outdoor", "mirror": False, "seasons": ["winter"],
                     "en": "on a street covered with fresh snow"},
}

# 요일(0=월) → 생활 · 장소 후보
WEEKDAYS: dict[int, dict] = {
    0: {"ko": "월", "life": "출근", "locations": ["elevator_mirror", "office_lobby", "subway_stairs", "entry_mirror", "subway_car"]},
    1: {"ko": "화", "life": "출근 + 퇴근 후 약속", "locations": ["elevator_mirror", "evening_alley", "restaurant_front", "campus", "convenience_store", "euljiro_alley"]},
    2: {"ko": "수", "life": "출근", "locations": ["elevator_mirror", "office_lobby", "subway_stairs", "entry_mirror", "library", "subway_car"]},
    3: {"ko": "목", "life": "출근 + 쇼핑", "locations": ["fitting_room", "street", "seongsu_street", "bookstore", "lecture_hall", "shutter_street"]},
    4: {"ko": "금", "life": "퇴근 후 데이트", "locations": ["crosswalk", "rooftop", "bar_front", "han_river", "amusement_park"]},
    5: {"ko": "토", "life": "카페·전시 · 나들이", "locations": ["cafe", "gallery_stairs", "park_bench", "beach", "mountain_view", "car", "autumn_foliage", "train_window", "airport", "snowy_street"]},
    6: {"ko": "일", "life": "집·동네 산책", "locations": ["room", "neighborhood_alley", "bakery_front", "han_river", "car", "campus", "shutter_street", "market_alley"]},
}

# 가게·간판이 있는 도심 장소(유리창 반사 셀카·캔디드 스트릿 컷)
URBAN = ["street", "evening_alley", "restaurant_front", "neighborhood_alley", "bakery_front", "bar_front", "seongsu_street", "convenience_store", "crosswalk", "shutter_street", "euljiro_alley", "market_alley"]

# ── 포즈(17) ─────────────────────────────────────────────────────────────
# feet: shoes(신발 보임) / socks(양말·맨발, 방 전용) / none(발 안 보임).
# where: 허용 장소 키 목록, 또는 kinds: 허용 장소 종류. mirror: 거울 필요. face: 얼굴 가림 방식.
POSES: dict[str, dict] = {
    "mirror_lean": {"self": True, "faces": ["phone", "chin_crop"], "ko": "미러셀카 한쪽 다리 기대기", "cut": "서기", "feet": "shoes", "mirror": True, "face": "phone",
                    "kinds": ["entry", "elevator", "fitting"],
                    "en": "taking a mirror selfie with her weight on one leg, full body visible in the mirror"},
    "mirror_back": {"self": True, "ko": "거울 앞 반쯤 돌아 뒷모습", "cut": "서기", "feet": "shoes", "mirror": True, "face": "phone",
                    "kinds": ["entry", "elevator", "fitting"],
                    "en": "standing half-turned away from the mirror to show the back of the outfit, glancing at the phone in the reflection"},
    "look_down": {"self": True, "ko": "내려다보기 셀카", "cut": "서기", "feet": "shoes", "face": "out_of_frame",
                  "kinds": ["entry", "elevator", "outdoor", "indoor", "fitting"],
                  "en": "a selfie shot looking straight down at her outfit and shoes from above"},
    "cafe_cross": {"ko": "카페 의자 다리 꼬기", "cut": "앉기", "feet": "shoes", "face": "shoulders", "where": ["cafe"],
                   "en": "sitting on a cafe chair with her legs crossed"},
    "stairs_sit": {"ko": "계단에 앉기", "cut": "앉기", "feet": "shoes", "face": "shoulders",
                   "where": ["subway_stairs", "gallery_stairs"], "en": "sitting casually on the steps"},
    "bench_side": {"ko": "벤치 옆 보기", "cut": "앉기", "feet": "shoes", "face": "shoulders", "where": ["park_bench"],
                   "en": "sitting on the bench, body turned to look off to the side"},
    "entry_shoes": {"ko": "현관 턱에서 신발 신기", "cut": "앉기", "feet": "shoes", "face": "shoulders", "where": ["entry_mirror"],
                    "en": "sitting on the entryway step putting on her shoes"},
    "bed_edge": {"ko": "침대 끝(양말)", "cut": "앉기", "feet": "socks", "face": "shoulders", "where": ["room"],
                 "en": "sitting on the edge of the bed wearing socks"},
    "floor_mirror": {"self": True, "ko": "바닥 거울 셀카(양말)", "cut": "앉기", "feet": "socks", "mirror": True, "face": "phone", "where": ["room"],
                     "en": "sitting on the floor in socks taking a mirror selfie in the floor mirror"},
    "crosswalk_walk": {"ko": "횡단보도 걷기", "cut": "걷기", "feet": "shoes", "face": "shoulders", "where": ["crosswalk"],
                       "en": "walking across the crosswalk mid-stride"},
    "walk_toward": {"ko": "카메라 쪽 두세 걸음", "cut": "걷기", "feet": "shoes", "face": "shoulders", "kinds": ["outdoor"],
                    "en": "walking two or three steps toward the camera"},
    "wall_back": {"ko": "벽에 등 기대기", "cut": "기대기", "feet": "shoes", "face": "shoulders",
                  "kinds": ["outdoor", "indoor", "elevator"], "en": "leaning her back against a wall"},
    "railing": {"ko": "난간에 팔 걸치기", "cut": "기대기", "feet": "none", "face": "shoulders",
                "where": ["rooftop", "gallery_stairs", "subway_stairs"], "en": "resting her forearms on a railing"},
    "tie_laces": {"ko": "신발 끈 묶기", "cut": "쪼그려", "feet": "shoes", "face": "shoulders", "kinds": ["outdoor", "entry"],
                  "en": "crouching down to tie her shoelaces"},
    "detail_bag": {"self": True, "ko": "가방·손 클로즈업", "cut": "디테일", "feet": "none", "face": "out_of_frame",
                   "kinds": ["outdoor", "indoor", "elevator", "entry", "fitting"],
                   "en": "a close-up of her hand holding the bag at hip height, showing the fabric of the outfit"},
    "sit_look_down": {"self": True, "ko": "앉아서 무릎·신발 내려다보기", "cut": "앉기", "feet": "shoes", "face": "out_of_frame",
                      "where": ["cafe", "park_bench", "subway_stairs", "gallery_stairs", "office_lobby", "car",
                                "train_window", "library", "lecture_hall", "han_river", "beach"],
                      "en": "a first-person shot from her own eyes while seated, looking down at her lap, legs and shoes, "
                            "her hand holding a coffee cup or phone at the edge of the frame"},
    "glass_reflection": {"self": True, "faces": ["phone", "chin_crop"], "ko": "가게 유리창에 비친 셀카", "cut": "서기", "feet": "shoes", "face": "phone",
                         "where": URBAN,
                         "en": "taking a selfie of her reflection in a shop's glass window, phone held up in front of "
                               "her face, the street faintly visible through the glass"},
    "mirror_crouch": {"self": True, "faces": ["phone", "chin_crop"], "ko": "거울 앞 쪼그려 미러셀카", "cut": "쪼그려", "feet": "shoes", "mirror": True, "face": "phone",
                      "kinds": ["entry", "elevator", "fitting"],
                      "en": "crouching slightly in front of the mirror taking a mirror selfie, phone covering her face"},
    # 대표 레퍼런스(2026-10-27) — 꾸안꾸 셀카 앵글
    "arm_selfie_high": {"self": True, "ko": "팔 뻗어 위에서 찍는 셀카", "cut": "서기", "feet": "none", "face": "chin_crop",
                        "kinds": ["outdoor", "indoor", "elevator", "entry", "fitting", "vehicle"],
                        "en": "a high-angle selfie with one arm stretched up toward the camera, looking down over her outfit "
                              "to about the knees, slightly tilted"},
    "closeup_sunglasses": {"self": True, "ko": "선글라스 클로즈업 셀카", "cut": "디테일", "feet": "none", "face": "sunglasses",
                           "force_eyewear": "sun", "kinds": ["outdoor", "indoor", "vehicle"],
                           "en": "a close-up selfie from the chest up, chin resting lightly on her hand, relaxed expression"},
    "wall_knee_camera": {"self": True, "ko": "벽에 기대 한쪽 무릎 들기(디카 들고)", "cut": "기대기", "feet": "shoes",
                         "face": "chin_crop", "kinds": ["indoor", "entry", "elevator", "fitting"],
                         "en": "standing against a plain wall with one knee bent up playfully, holding a compact silver "
                               "digital camera at chest height, shot on a phone timer from waist level"},
    "cafe_terrace": {"self": True, "ko": "카페 테라스에 앉아 아아 들고", "cut": "앉기", "feet": "none", "face": "sunglasses",
                     "where": ["cafe", "street", "bakery_front", "restaurant_front"],
                     "tail": "A casual phone snapshot a friend took across the table — not a photoshoot, unposed.",
                     "en": "sitting at an outdoor cafe table holding an iced americano, looking away down the street"},
    # 얼굴 셀카(대표 2026-10-27 "가끔은 이쁜 얼굴도, 셀카는 얼굴만 가까이도 찍잖아") — 가끔만(FACE_SHOT_RATE)
    "face_selfie": {"self": True, "ko": "얼굴 가까이 셀카", "cut": "얼굴", "feet": "none", "face": "full",
                    "kinds": ["room", "indoor", "outdoor", "elevator", "entry", "fitting", "vehicle"],
                    "en": "a close-up front-camera selfie of her face and shoulders, phone held at arm's length slightly "
                          "above eye level, head tilted a little, soft natural light on her face"},
    # 캔디드·파파라치(대표 2026-10-27 "가끔은 누가 도촬하듯, 스트릿 파파라치") — group=candid, 가끔만
    "candid_shutter_lean": {"self": True, "group": "candid", "ko": "셔터에 등 기대고 앞 보기(캔디드)", "cut": "기대기",
                            "feet": "shoes", "face": "profile", "where": URBAN,
                            "en": "leaning her back against a closed metal roller shutter, looking ahead down the street, "
                                  "not at the camera"},
    "candid_curb_sit": {"self": True, "group": "candid", "ko": "길가 턱에 앉아 앞 보기(캔디드)", "cut": "앉기",
                        "feet": "shoes", "face": "profile", "where": URBAN,
                        "en": "sitting on a low step at the edge of the street, looking ahead at something, unaware of "
                              "the camera"},
    "studio_full_body": {"self": True, "group": "studio", "ko": "스튜디오 전신(눈높이)", "cut": "서기", "feet": "shoes",
                         "face": "full", "kinds": ["studio"],
                         "en": "standing naturally and relaxed, facing the camera with a slight hip shift, hands loose or "
                               "in pockets, the whole body from head to toe in frame with space above and below, shot at "
                               "chest height from a few meters away with a 50mm lens so her proportions look true and long",
                         "tail": "A clean modern fashion lookbook photo: soft diffused daylight, a gentle shadow on the "
                                 "floor, natural true-to-life colors, crisp but not oversharpened, no retouching."},
    "paparazzi_walk": {"self": True, "group": "candid", "ko": "길 건너에서 찍힌 파파라치 워킹", "cut": "걷기",
                       "feet": "shoes", "face": "profile", "where": URBAN + ["campus", "han_river", "crosswalk"],
                       "en": "walking mid-stride and glancing to the side, captured from across the street with a "
                             "telephoto lens, passers-by softly blurred in the foreground"},
    "toe_down": {"self": True, "ko": "발끝 내려다보기", "cut": "디테일", "feet": "shoes", "face": "out_of_frame",
                 "kinds": ["outdoor", "entry", "elevator"],
                 "en": "a shot looking down at her feet, showing the shoes and the hem of the bottoms"},
    "flatlay": {"self": True, "ko": "플랫레이(사람 없음)", "cut": "디테일", "feet": "none", "face": "none", "person": False,
                "kinds": ["room", "entry"], "en": "a flat lay of the outfit items arranged neatly"},
}

# 자유분방(대표 2026-10-27 "좀 더 자유분방했으면") — 컷마다 하나 섞는 순간·연출(70%).
# 머리카락이 얼굴·화면을 덮는 '바람 머리'도 뺐다(2026-10-28, 03번 컷).
# 흔들림·초점 나간 연출은 뺐다(대표 2026-10-27: 팔·다리가 흐려 옷이 안 보임).
# face: 얼굴(입술 포함)이 보일 때만 쓰는 표정.
MOODS = [
    {"en": "caught mid-laugh in a spontaneous moment"},
    {"en": "making a playful peace sign with her free hand"},
    {"en": "shot with the on-camera flash at night, a little overexposed, Y2K party-snapshot feel"},
    {"en": "a tilted, carefree angle like she snapped it in a hurry"},
    {"en": "a cute pouty lips expression", "face": True},
    {"en": "biting her lip with a cheeky half smile", "face": True},
    {"en": "a big carefree smile", "face": True},
]
MOOD_RATE = 0.7

# 얼굴 공개 셀카 비율 — 4~5장에 1장, 연속 금지(대표 2026-10-27). 나머지 컷은 눈을 가린다.
FACE_SHOT_RATE = 0.22
# 얼굴을 가리는 비율(대표 2026-10-27) — 20%만 가리고(폰·눈 아래 크롭·선글라스) 나머지는 얼굴이 보인다.
FACE_HIDE_RATE = 0.2
# 캔디드·파파라치 비율(대표 2026-10-27) — 5장에 1장꼴, 연속 금지. 장소가 도심이 아니면 셀카로.
CANDID_RATE = 0.2

# 소품(절반 확률, 디테일·플랫레이 제외) — 대표 레퍼런스의 아아·디카 느낌
PROPS = ["holding an iced americano", "holding a compact silver digital camera", "earphones in, phone in one hand"]

# 대표 피드백(2026-10-27): "모델처럼 남이 찍어 준 느낌" 말고 **스스로 찍은 셀카 느낌**만.
# 미러셀카·유리창 반사·내려다보기(1인칭)·디테일·플랫레이만 쓰고, 제3자 시점 포즈(벤치 옆 보기·걷기·벽 기대기 등)는 끈다.
SELF_SHOT_ONLY = True

# ── 아이웨어 7종 × 착용 4방식 ─────────────────────────────────────────────
EYEWEAR: dict[str, dict] = {
    "black_sunglasses": {"ko": "블랙 선글라스", "en": "classic black sunglasses", "sun": True},
    "tortoise_sunglasses": {"ko": "호피 선글라스", "en": "tortoiseshell sunglasses", "sun": True},
    "cateye_sunglasses": {"ko": "캣아이 선글라스", "en": "cat-eye sunglasses", "sun": True},
    "slim_sunglasses": {"ko": "슬림 사각 선글라스", "en": "slim rectangular sunglasses", "sun": True},
    "metal_round": {"ko": "얇은 메탈 원형 안경", "en": "thin gold metal round glasses", "sun": False},
    "clear_acetate": {"ko": "투명 뿔테 안경", "en": "clear acetate glasses", "sun": False},
    "brown_tint": {"ko": "브라운 틴트 안경", "en": "glasses with light brown tinted lenses", "sun": False},
}
EYEWEAR_STYLES: dict[str, dict] = {
    "wear": {"ko": "쓰기", "en": "She is wearing {item}."},
    "head": {"ko": "머리 위", "en": "She has {item} pushed up on top of her head."},
    "neckline": {"ko": "넥라인", "en": "She has {item} hooked on the neckline of her top."},
    "hand": {"ko": "손", "en": "She is holding {item} in one hand."},
}

# 헤어 키워드 → 어울리는 상황(Claude 에 힌트로만)
HAIR_HINTS = {
    "lowbun": "출근룩", "halfup": "출근룩·데이트", "straight": "기본", "wave": "데이트·주말", "ponytail": "스트릿·활동",
    "cap": "스트릿·주말", "beanie": "겨울", "clawclip": "집·주말", "braid": "주말·여행", "beret": "가을·겨울 데이트",
    "headband": "주말",
}

PRODUCT_KINDS = {
    "top": ("상의", "the top"), "bottoms": ("하의", "the bottoms"), "dress": ("원피스", "the dress"),
    "outerwear": ("아우터", "the outerwear"), "shoes": ("신발", "the shoes"), "bag": ("가방", "the bag"),
    "accessory": ("액세서리", "the accessory"),
}


def season_of(d: date) -> str:
    return {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer"}.get(d.month, "autumn")


SEASON_WEATHER = {
    "spring": "a mild spring day with soft light", "summer": "a bright summer day",
    "autumn": "a crisp autumn day", "winter": "a cold clear winter day",
}
SEASON_KO = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}


# ── 규칙 ─────────────────────────────────────────────────────────────────
def compatible(pose_key: str, loc_key: str) -> bool:
    """포즈 ↔ 장소 상식 규칙. 신발 보이는 포즈는 방 금지, 양말은 방 전용, 거울 포즈는 거울 장소."""
    pose, loc = POSES[pose_key], LOCATIONS[loc_key]
    if SELF_SHOT_ONLY and not pose.get("self"):
        return False
    if "where" in pose and loc_key not in pose["where"]:
        return False
    if "kinds" in pose and loc["kind"] not in pose["kinds"]:
        return False
    if pose.get("mirror") and not loc.get("mirror"):
        return False
    if pose["feet"] == "shoes" and loc["kind"] == "room":
        return False
    if pose["feet"] == "socks" and loc["kind"] != "room":
        return False
    return True


def _blocked_by_streak(history: list[dict], field: str) -> set:
    """최근 2개가 같은 값이면 그 값은 이번에 금지(3연속 금지). history 는 최신순."""
    vals = [((h.get("plan") or {}).get(field)) for h in history[:2]]
    return {vals[0]} if len(vals) == 2 and vals[0] and vals[0] == vals[1] else set()


def _entry_mirror_week(history: list[dict], now: datetime) -> int:
    since = now - timedelta(days=7)
    n = 0
    for h in history:
        try:
            t = datetime.fromisoformat(str(h.get("created_at")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if t >= since and (h.get("plan") or {}).get("location") == "entry_mirror":
            n += 1
    return n


def choose_eyewear(history: list[dict], rng: random.Random, override: str | None = None) -> dict | None:
    """3번 중 1번 정도: 직전 2번 모두 없음 → 씀 / 직전에 씀 → 안 씀 / 그 외 30%. 같은 아이템 연속 금지."""
    if override == "none":
        return None
    recent = [(h.get("plan") or {}).get("eyewear") for h in history[:2]]
    # 같은 아이템 연속 금지 — 직전 '착용한' 착장의 아이템과 비교(바로 앞 착장은 대개 안 쓴 날이다)
    worn = [(h.get("plan") or {}).get("eyewear") for h in history if (h.get("plan") or {}).get("eyewear")]
    last_item = worn[0].get("item") if worn else None
    if override and override in EYEWEAR:
        item = override
    else:
        if recent and recent[0]:
            return None
        if not (len(recent) == 2 and not recent[0] and not recent[1]) and rng.random() >= 0.3:
            return None
        choices = [k for k in EYEWEAR if k != last_item]
        item = rng.choice(choices)
    style = rng.choice(list(EYEWEAR_STYLES))
    return {"item": item, "style": style}


FACE_MODES = {"phone", "chin_crop", "sunglasses", "full", "mirror_full", "profile", "out_of_frame"}


def choose_face(pose_key: str, rng: random.Random) -> str:
    """얼굴 처리(대표 2026-10-27: 가리는 건 20%, 나머지는 얼굴 보여도 됨).
    발·디테일·플랫레이처럼 원래 얼굴이 없는 컷은 그대로, 캔디드는 옆모습, 선글라스 클로즈업은 선글라스."""
    pose = POSES[pose_key]
    base = pose["face"]
    if base in ("out_of_frame", "none") or pose.get("person") is False:
        return base
    if pose.get("group") == "candid":
        return "profile"
    if base == "full" or pose.get("force_eyewear") == "sun":
        return "full" if base == "full" else "sunglasses"
    if rng.random() < FACE_HIDE_RATE:
        return rng.choice(pose.get("faces") or [base])
    return "mirror_full" if (pose.get("mirror") or pose_key == "glass_reflection") else "full"


def candidates(*, weekday: int, products: list[dict], hair_roles: list[str], history: list[dict],
               now: datetime, location: str | None = None, pose: str | None = None,
               cut: str | None = None, hair: str | None = None) -> dict:
    """규칙으로 거른 후보: {pairs: [(loc, pose)], hairs: [...], notes: [...]}. 대표 지정값은 그대로 존중하되
    규칙 위반 조합은 만들지 않는다."""
    notes: list[str] = []
    has_shoes = any(p.get("kind") == "shoes" for p in products)
    locs = [location] if location in LOCATIONS else list(WEEKDAYS[weekday]["locations"])
    if not location:
        season = season_of(now.astimezone(KST).date())
        locs = [x for x in locs if season in LOCATIONS[x].get("seasons", [season])] or locs   # 단풍길은 가을만 등
        blocked = _blocked_by_streak(history, "location")
        if _entry_mirror_week(history, now) >= 2:
            blocked.add("entry_mirror")
            notes.append("현관 거울은 이번 주 2회 사용 — 제외")
        keep = [x for x in locs if x not in blocked]
        locs = keep or locs
        if has_shoes:
            no_room = [x for x in locs if LOCATIONS[x]["kind"] != "room"]
            if no_room:
                locs = no_room
            else:
                notes.append("신발 상품이 있지만 방 장소뿐 — 신발은 빼고 양말 컷")
    poses = [pose] if pose in POSES else [k for k, v in POSES.items() if not cut or v["cut"] == cut]
    if not pose:
        blocked = _blocked_by_streak(history, "pose")
        poses = [p for p in poses if p not in blocked] or poses
        if not any(p.get("kind") == "bag" for p in products):
            poses = [p for p in poses if p != "detail_bag"] or poses
    pairs = [(lk, pk) for lk in locs for pk in poses if compatible(pk, lk)]
    if not pairs and (location or pose):  # 대표 지정이 규칙과 충돌 → 지정 하나만 살리고 나머지 자동
        notes.append("지정한 장소·포즈 조합이 장면 규칙과 맞지 않아 자동으로 맞췄어요")
        fixed_locs = [location] if location in LOCATIONS else list(WEEKDAYS[weekday]["locations"])
        pairs = [(lk, pk) for lk in fixed_locs for pk in POSES if compatible(pk, lk)]
        if not pairs:
            pairs = [(lk, pk) for lk in WEEKDAYS[weekday]["locations"] for pk in POSES if compatible(pk, lk)]
    hairs = [hair] if hair in hair_roles else list(hair_roles)
    if not hair:
        blocked = _blocked_by_streak(history, "hair_role")
        hairs = [h for h in hairs if h not in blocked] or hairs
    return {"pairs": pairs, "hairs": hairs, "notes": notes}


# ── 기획(Claude) ─────────────────────────────────────────────────────────
_PLAN_SYSTEM = (
    "You plan ONE everyday Instagram outfit photo for a Korean fashion account (an original virtual woman). "
    "Pick from the given options only and return ONE JSON object: "
    '{"pair": <index of the location/pose pair>, "hair_role": "<one of hairs or empty>", '
    '"weather_en": "<short English weather/light phrase matching the season>", '
    '"reason": "<한국어 한 줄: 왜 이 장소·포즈·헤어인지>"}. '
    "Match the outfit to the day's life (commute look → office places, date → evening places), the season, and "
    "the product types. Prefer variety versus the recent history — mix city, campus, nature (beach, mountain, "
    "river), transport (car, train, subway) and home across the week."
)


def _summary(products: list[dict]) -> list[dict]:
    return [{"kind": p.get("kind"), "desc": p.get("desc") or ""} for p in products]


def plan_scene(*, character_id: str, products: list[dict], hair_roles: list[str], history: list[dict],
               options: dict | None = None, now: datetime | None = None, rng: random.Random | None = None,
               llm=None) -> dict:
    """장면 기획 → plan dict. llm(system, user) -> str 은 테스트에서 주입(기본 Claude via music_lyrics._call)."""
    options = options or {}
    rng = rng or random.Random()
    now = now or datetime.now(KST)
    weekday = int(options["weekday"]) if str(options.get("weekday", "")).isdigit() and 0 <= int(options["weekday"]) <= 6 \
        else now.astimezone(KST).weekday()
    season = options.get("season") if options.get("season") in SEASON_WEATHER else season_of(now.astimezone(KST).date())
    cand = candidates(weekday=weekday, products=products, hair_roles=hair_roles, history=history, now=now,
                      location=options.get("location") or None, pose=options.get("pose") or None,
                      cut=options.get("cut") or None, hair=options.get("hair") or None)
    eyewear = choose_eyewear(history, rng, options.get("eyewear") or None)
    pairs, hairs = cand["pairs"], cand["hairs"]
    if not pairs:
        raise ValueError("장면 규칙을 만족하는 장소·포즈 조합이 없어요.")
    if not options.get("location") and rng.random() >= NIGHT_RATE:   # 밤 장소는 가끔만
        pairs = [pr for pr in pairs if pr[0] not in NIGHT_LOCATIONS] or pairs
    # 얼굴 셀카는 가끔만: 이번에 넣을지 먼저 정하고(직전이 얼굴 셀카면 안 넣음), 아니면 후보에서 뺀다.
    if not options.get("pose"):
        # 컷 종류를 먼저 정한다: 얼굴 셀카(가끔) / 캔디드·파파라치(가끔) / 셀카(기본). 같은 특별 컷 연속 금지.
        def group(pk):
            return "face" if POSES[pk].get("face") == "full" else POSES[pk].get("group", "self")
        last = group(history[0]["plan"]["pose"]) if history and (history[0].get("plan") or {}).get("pose") in POSES else None
        r = rng.random()
        want = "face" if r < FACE_SHOT_RATE else ("candid" if r < FACE_SHOT_RATE + CANDID_RATE else "self")
        if want == last and want != "self":
            want = "self"
        chosen = [pr for pr in pairs if group(pr[1]) == want]
        pairs = chosen or [pr for pr in pairs if group(pr[1]) == "self"] or pairs

    pick, hair_role, weather, reason, source = None, None, None, "", "random"
    if llm is None:
        from services import music_lyrics
        llm = lambda s, u: music_lyrics._call(s, u, max_tokens=400, task="insta_plan")  # noqa: E731
    recent = [{k: (h.get("plan") or {}).get(k) for k in ("location", "pose", "hair_role")} for h in history[:5]]
    user = json.dumps({
        "weekday": WEEKDAYS[weekday]["ko"], "life": WEEKDAYS[weekday]["life"], "season": season,
        "products": _summary(products),
        "pairs": [{"i": i, "location": LOCATIONS[l]["ko"], "pose": POSES[p]["ko"]} for i, (l, p) in enumerate(pairs)],
        "hairs": [{"role": h, "suits": HAIR_HINTS.get(h.split("_")[-1], "")} for h in hairs],
        "recent": recent,
    }, ensure_ascii=False)
    try:
        from services import music_lyrics
        data = music_lyrics._extract_json(llm(_PLAN_SYSTEM, user))
        i = int(data.get("pair"))
        if 0 <= i < len(pairs):
            pick = pairs[i]
            source = "ai"
        hr = str(data.get("hair_role") or "")
        hair_role = hr if hr in hairs else None
        weather = str(data.get("weather_en") or "")[:80] or None
        reason = str(data.get("reason") or "")[:160]
    except Exception as e:  # noqa: BLE001 - 기획 실패가 생성을 막지 않게 규칙 후보에서 무작위
        logger.warning("[insta-plan] Claude 기획 실패 → 무작위: %s", str(e)[:200])
    if pick is None:
        pick = rng.choice(pairs)
        reason = reason or "규칙 후보 중 무작위 선택"
    if hair_role is None and hairs:
        hair_role = rng.choice(hairs)
    loc, pose = pick
    face = options.get("face") if options.get("face") in FACE_MODES else choose_face(pose, rng)
    if POSES[pose].get("force_eyewear") == "sun" or face == "sunglasses":
        if not (eyewear and EYEWEAR[eyewear["item"]]["sun"] and eyewear["style"] == "wear"):
            eyewear = {"item": rng.choice([k for k, v in EYEWEAR.items() if v["sun"]]), "style": "wear"}
        face = "sunglasses"
    prop = None if POSES[pose].get("person") is False or POSES[pose]["cut"] == "디테일" else (
        rng.choice(PROPS) if rng.random() < 0.5 else None)
    mood = None
    if POSES[pose].get("person") is not False and rng.random() < MOOD_RATE:
        lips = face in ("full", "chin_crop", "sunglasses", "profile", "mirror_full")
        mood = rng.choice([m for m in MOODS if lips or not m.get("face")])["en"]
    return {
        "face": face, "prop": prop, "mood": mood, "styling_en": (str(options.get("styling_en") or "")[:120] or None),
        "weekday": weekday, "weekday_ko": WEEKDAYS[weekday]["ko"], "life": WEEKDAYS[weekday]["life"],
        "location": loc, "location_ko": LOCATIONS[loc]["ko"], "pose": pose, "pose_ko": POSES[pose]["ko"],
        "cut": POSES[pose]["cut"], "hair_role": hair_role, "eyewear": eyewear,
        "eyewear_ko": (f"{EYEWEAR[eyewear['item']]['ko']} · {EYEWEAR_STYLES[eyewear['style']]['ko']}" if eyewear else None),
        "season": season, "season_ko": SEASON_KO[season], "weather_en": weather or SEASON_WEATHER[season],
        "reason": reason, "source": source, "notes": cand["notes"],
    }


# ── 프롬프트 ─────────────────────────────────────────────────────────────
# 사실감(대표 2026-10-27 "너무 AI 같다" + GPT Image 실사 프롬프트 참고): 구체적인 촬영 방식·빛의 출처·피부결을
# 적고, 과장되던 지시(노출 불균형·잡동사니·광각 왜곡)는 뺀다. AI 티는 시네마틱 보정·HDR·과샤픈에서 난다.
_SHOT = ("A realistic vertical smartphone snapshot — handheld, subject slightly off-center, natural candid framing, "
         "true-to-life proportions.")
_SKIN = ("Real skin with natural texture and fine pores — no airbrushing, no plastic or waxy skin. Fabrics show real "
         "texture and subtle natural creases.")
_TAIL = ("Shot on an iPhone main camera: true-to-life colors, clean natural exposure, faint mobile sensor noise, the "
         "background in natural soft focus — no cinematic color grading, no HDR glow, no oversharpening, no beauty filter.")

# 장소별 빛의 출처·바닥/벽 재질(구체적일수록 실사처럼). 없으면 종류별 기본.
LIGHT = {
    "entry_mirror": "soft daylight from a nearby window, beige tile floor, white walls",
    "elevator_mirror": "even overhead elevator LED light, brushed metal and mirror panels",
    "fitting_room": "warm even fitting-room lighting, a neutral curtain behind",
    "evening_alley": "warm light spilling from shop windows onto her, faint blue dusk sky, clean exposure",
    "restaurant_front": "warm entrance light falling on her softly, the street still lit by the last daylight",
    "bar_front": "warm soft light from the bar doorway lighting her evenly, clean exposure without harsh shadows",
    "convenience_store": "bright white light from the convenience-store windows lighting her evenly, clean exposure",
    "euljiro_alley": "soft late-afternoon daylight in the alley with a few warm shop lights, worn concrete underfoot",
    "market_alley": "soft daylight under the market canopy mixed with warm hanging bulbs",
    "shutter_street": "soft overcast daylight on the colorful roller shutters, asphalt underfoot",
    "subway_car": "cool even fluorescent light inside the train, metal poles and window reflections",
    "subway_stairs": "soft daylight at the station exit, grey stone steps",
    "white_studio": "large soft diffused light from the front-left, even and flattering, no harsh shadows",
    "amusement_park": "golden late-afternoon sunlight with colorful rides softly out of focus",
}
LIGHT_BY_KIND = {
    "studio": "large soft diffused studio light",
    "outdoor": "soft natural daylight (overcast or late afternoon), gentle shadows",
    "indoor": "soft daylight from large windows mixed with warm interior light",
    "vehicle": "soft daylight through the windows",
    "room": "soft morning daylight from the window",
    "entry": "soft daylight from a nearby window",
    "elevator": "even overhead LED light",
    "fitting": "warm even fitting-room lighting",
}
NIGHT_LOCATIONS = {"evening_alley", "restaurant_front", "bar_front", "convenience_store"}
NIGHT_RATE = 0.25   # 밤·저녁 장소는 가끔만(어두운 장면에서 AI 티가 가장 많이 남)


def light_line(location: str) -> str:
    loc = LOCATIONS[location]
    return f"Lighting: {LIGHT.get(location) or LIGHT_BY_KIND.get(loc['kind'], LIGHT_BY_KIND['outdoor'])}."
_SELF_TAIL = ("She took this photo herself with her own phone for her Instagram — a casual, unposed self-shot, not a "
              "photographer's or model shoot: natural relaxed stance, slightly tilted, imperfect off-center framing. "
              "It feels like a page from her everyday photo diary.")
_CANDID_TAIL = ("A candid street shot, as if a friend or a street-style photographer caught her without her noticing — "
                "documentary feel, natural light, shallow depth of field, real Seoul street atmosphere.")
# 분위기는 옷·스타일링에만 — 얼굴을 '평균 20대 얼굴'로 끌고 가지 않게(대표 2026-10-27: 기준 얼굴과 다르게 나옴)
_YOUTH = ("Her styling has a hip early-20s Seoul street vibe (Seongsu, Hongdae) — fresh, never mature or matronly; "
          "casual, slightly undone hair styling. Her face itself stays exactly as in reference image 1.")


def body_line(m: dict | None) -> str:
    """체형 — 참조 2(체형 사진) 비율을 따르게. 2026-10-28: 가슴-허리-엉덩이 숫자는 Muse 안전 필터에 걸려
    (Content flagged as potentially sensitive) 키만 넣는다 — 체형은 참조 사진이 전달한다."""
    nums = f" ({m['height']:g} cm tall)" if m and m.get("height") else ""
    return (f"Her body proportions match reference image 2{nums}; the clothes fit her naturally the way they would "
            "on her real figure.")
_MAKEUP = "Natural everyday makeup: light dewy base and a soft rosy lip tint — nothing heavy."
_EFFORTLESS = ("Effortless, not overdressed (꾸안꾸): the clothes sit naturally on her with her own silhouette, minimal "
               "accessories — at most a thin necklace or small earrings, no pearls or brooches.")
_DETAIL = "keep every garment detail identical: color, fabric texture, buttons, pattern, neckline, length and fit"


def _product_phrase(kind: str, n: int) -> str:
    noun = PRODUCT_KINDS.get(kind, ("", "the item"))[1]
    return f"carrying {noun} from image {n}" if kind == "bag" else f"{noun} from image {n}"


def _face_line(plan: dict) -> str:
    pose = POSES[plan["pose"]]
    ew = plan.get("eyewear")
    face = plan.get("face") or pose["face"]
    if face == "phone":
        return "phone held up covering her face"
    if face == "out_of_frame":
        return "her face is not in the frame"
    if face == "mirror_full":
        return ("holding the phone low at chest height so her whole face is visible in the mirror — it must look exactly "
                "like reference image 1 (same eyes, nose, lips, face shape and moles)")
    if face == "profile":
        return "seen in side profile, looking off ahead and not at the camera"
    if face == "full":
        return ("her whole face is visible and pretty — it must look exactly like reference image 1 (same eyes, nose, "
                "lips, face shape and moles)")
    if face == "chin_crop":
        return ("the top edge of the frame cuts across her face just below the eyes, so only the tip of her nose, her "
                "lips and chin show — her eyes are never visible")
    if face == "sunglasses" or (ew and ew["style"] == "wear" and EYEWEAR[ew["item"]]["sun"]):
        return "her eyes hidden behind the sunglasses, only the lower part of her face visible, face turned slightly away"
    return "framed from the shoulders down so her face is not visible"


def build(plan: dict, *, face_url: str, body_url: str, hair_url: str | None, products: list[dict],
          fix_hint: str | None = None, measurements: dict | None = None, safe: bool = False,
          pose_ref: dict | None = None) -> tuple[str, list[str]]:
    """safe=True: 안전 필터에 걸린 뒤 다시 보낼 때 — 체형·피부·분위기 문장을 빼고 단순하게.
    pose_ref(포즈 라이브러리, 2026-10-30): {"url", "en"} — 마네킹 선화를 참고 이미지로 넣고 포즈 문장을 대체."""
    """(prompt, refs). 참조 순서 고정 ① face ② body ③ hair ④~ 상품. 방(양말) 컷은 신발 상품을 뺀다."""
    loc = LOCATIONS[plan["location"]]
    pose = POSES[plan["pose"]]
    use = [p for p in products if not (p.get("kind") == "shoes" and (loc["kind"] == "room" or pose["feet"] == "socks"))]
    weather = plan.get("weather_en") or SEASON_WEATHER.get(plan.get("season", ""), "")

    if pose.get("person") is False:  # 플랫레이 — 사람 없음, 상품만 참조
        refs = [p["url"] for p in use][:MAX_REFS]
        items = ", ".join(_product_phrase(p.get("kind", ""), i + 1).replace("carrying ", "") for i, p in enumerate(use[:MAX_REFS]))
        surface = "the light grey entryway tiles of a Korean apartment" if loc["kind"] == "entry" else "a neatly made white bed"
        prompt = (f"Flat lay photo with no person: {items} arranged neatly on {surface}, shot from directly above, {weather}. "
                  f"Take only the items from the product images — {_DETAIL}. {_TAIL}")
    else:
        refs = [face_url, body_url] + ([hair_url] if hair_url else [])
        pose_idx = None
        if pose_ref and pose_ref.get("url"):
            refs.append(pose_ref["url"])
            pose_idx = len(refs)
        start = len(refs) + 1
        room = MAX_REFS - len(refs)
        use = use[:room]
        refs += [p["url"] for p in use]
        hair_part = "with the hairstyle from image 3" if hair_url else "with her usual long black hair"
        wear = ", ".join(_product_phrase(p.get("kind", ""), start + i) for i, p in enumerate(use))
        parts = [
            _SHOT,
            "Her face is exactly the woman in reference image 1 — same eyes, nose, lips, jawline, face shape and moles, "
            f"clearly recognisable as the same person; only the hairstyle may differ ({hair_part}, black hair color).",
            *([] if safe else [body_line(measurements)]),
            "Reference image 2 shows only her body shape — never copy the plain grey ribbed top or grey leggings "
            "she wears there; she wears only the outfit described here.",
            "Take only the clothing from the product images — ignore the body and face of any model wearing them. "
            f"She is wearing exactly {wear} — {_DETAIL}.",
            _YOUTH,
        ]
        if plan.get("styling_en"):
            parts.append(f"She also wears {plan['styling_en']}.")
        if any(p.get("revealing") for p in use):
            parts.append("She wears a plain fitted top underneath.")
        if loc["kind"] == "room" or pose["feet"] == "socks":
            parts.append("She is in socks, no shoes.")
        ew = plan.get("eyewear")
        if ew:
            parts.append(EYEWEAR_STYLES[ew["style"]]["en"].format(item=EYEWEAR[ew["item"]]["en"]))
        if plan.get("prop"):
            parts.append(f"She is {plan['prop']}.")
        if plan.get("mood") and not safe:
            parts.append(f"Free-spirited mood: {plan['mood']}.")
        if pose_idx:
            desc = f" ({pose_ref['en'].strip().rstrip('.')})" if pose_ref.get("en") else ""
            parts.append(
                f"Her body pose copies the grey faceless mannequin sketch in reference image {pose_idx}{desc} — "
                "same arm, leg, torso and head positions and the same camera angle. Take only the pose from that "
                "image: never its grey colour, outlines, blank face, bare body or plain background.")
            parts.append(f"{loc['en'][:1].upper()}{loc['en'][1:]}, {_face_line(plan)}, {weather}.")
        else:
            parts.append(f"{pose['en'][:1].upper()}{pose['en'][1:]}, {loc['en']}, {_face_line(plan)}, {weather}.")
        parts.append(light_line(plan["location"]))
        if not safe:
            parts.append(_SKIN)
        if (plan.get("face") or pose["face"]) in ("chin_crop", "sunglasses", "full", "profile", "mirror_full"):
            parts.append(_MAKEUP)
        parts.append(_EFFORTLESS)
        if pose.get("group") == "candid":
            parts.append(_CANDID_TAIL)
        elif pose.get("tail"):
            parts.append(pose["tail"])
        elif pose.get("self"):
            parts.append(_SELF_TAIL)
        parts.append(_TAIL)
        prompt = " ".join(parts)
    if fix_hint:
        prompt += f" Important fix from the last attempt: {fix_hint.strip().rstrip('.')}."
    return prompt, refs
