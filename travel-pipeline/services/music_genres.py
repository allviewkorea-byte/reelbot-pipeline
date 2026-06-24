"""장르 체계 SSOT (#45) — 14장르 마스터 목록 + 분류·프리셋.

이 모듈은 음악 채널의 **재생목록/분류 카테고리** 14종을 한 곳에 정의한다.
다른 모든 백엔드 지점(수동 렌더·테스트 렌더 프리셋, 큐 분류 등)이 여기를 참조한다.
프론트엔드는 동일 목록을 `src/lib/music-genres.ts` 에 상수로 둔다(둘을 함께 갱신).

설계 메모(하위호환):
- 장르는 DB(music_uploads.genre, mood)에 **자유 텍스트**로 저장된다(enum/제약 없음).
  따라서 14장르는 *저장 형태가 아니라 분류·표시 레이어*다 — 마이그레이션 불필요.
- 기존 5분류(시티팝/드라이브·카페/재즈·이별/발라드·운동/동기부여·수면/공부)로
  저장된 행은 raw genre 라벨을 그대로 표시하고, 아래 키워드로 14장르 버킷에 매핑된다.
  (예: 옛 genre="EDM"+situation="운동" → workout, "Lo-fi"+"수면 공부" → sleep_study)

범위 주의(#45): 여기는 장르 *체계*만. Suno 태그/style_prompt 의 본격 매핑은 #46,
이미지 프롬프트 연결은 #47. 아래 프리셋의 style_prompt 는 기존 5프리셋과 동일한
수준의 짧은 placeholder 로, 수동/테스트 파이프라인 동작에 필요한 최소값이다.
"""

from __future__ import annotations

# ── 14장르 마스터 목록 (확정) ──────────────────────────────────────────
# suno_tags/instrumental/bpm_range(#46-C): 장르별 고정 Suno 스타일. 값 출처는
# docs/revezen_genre_prompt_pool.md. id/label_kr/label_en 은 #45 그대로(무수정).
GENRES: list[dict] = [
    {"id": "citypop", "label_kr": "시티팝", "label_en": "City Pop",
     "suno_tags": "city pop, 80s japanese funk, warm analog synth, slap bass, groovy, nostalgic summer",
     "instrumental": False, "bpm_range": "95-110"},
    {"id": "sunset_drive", "label_kr": "선셋 드라이브", "label_en": "Sunset Drive",
     "suno_tags": "synthwave, sunset drive, retro wave, warm pads, electric guitar, dreamy, nostalgic cruise",
     "instrumental": False, "bpm_range": "85-100"},
    {"id": "morning_drive", "label_kr": "모닝 드라이브", "label_en": "Morning Drive",
     "suno_tags": "upbeat pop, morning drive, acoustic guitar, bright synth, feel good, sunny day, fresh start",
     "instrumental": False, "bpm_range": "105-120"},
    {"id": "cafe", "label_kr": "카페", "label_en": "Café",
     "suno_tags": "cafe acoustic, bossa nova, gentle guitar, warm atmosphere, coffee shop ambience, relaxing afternoon",
     "instrumental": False, "bpm_range": "80-95"},
    {"id": "jazz", "label_kr": "재즈", "label_en": "Jazz",
     "suno_tags": "smooth jazz, saxophone solo, walking bass, brushed drums, piano trio, late night club, sophisticated",
     "instrumental": False, "bpm_range": "90-120"},
    {"id": "ballad", "label_kr": "발라드", "label_en": "Ballad",
     "suno_tags": "korean ballad, emotional piano, strings orchestra, heartfelt, warm vocal, cinematic, touching",
     "instrumental": False, "bpm_range": "65-85"},
    {"id": "breakup", "label_kr": "이별", "label_en": "Breakup",
     "suno_tags": "sad ballad, minor key, emotional piano, rain ambience, melancholic strings, lonely night, heartbreak",
     "instrumental": False, "bpm_range": "60-75"},
    {"id": "workout", "label_kr": "운동/동기부여", "label_en": "Workout",
     "suno_tags": "workout EDM, high energy, powerful bass drops, motivational, fast tempo, gym anthem, uplifting",
     "instrumental": False, "bpm_range": "130-150"},
    {"id": "sleep_study", "label_kr": "수면/공부", "label_en": "Study & Sleep",
     "suno_tags": "ambient study, soft piano, gentle rain, minimal texture, calming, deep focus, peaceful night",
     "instrumental": False, "bpm_range": "55-70"},
    {"id": "lofi", "label_kr": "로파이", "label_en": "Lo-fi",
     "suno_tags": "lofi hip hop, vinyl crackle, jazzy piano, mellow beats, chill vibe, rainy window, warm room",
     "instrumental": False, "bpm_range": "70-85"},
    {"id": "kpop", "label_kr": "K-pop", "label_en": "K-pop",
     "suno_tags": "kpop, catchy hook, synth pop, dance beat, korean style, bright energy, addictive melody",
     "instrumental": False, "bpm_range": "110-130"},
    {"id": "pop", "label_kr": "팝송", "label_en": "Pop",
     "suno_tags": "american pop, catchy melody, modern production, radio hit, upbeat vocal, feel good anthem",
     "instrumental": False, "bpm_range": "100-125"},
    {"id": "rnb_soul", "label_kr": "R&B/소울", "label_en": "R&B Soul",
     "suno_tags": "neo soul, rnb groove, silky vocals, rhodes piano, slow jam, intimate night, smooth bass, 90s vibe",
     "instrumental": False, "bpm_range": "75-95"},
    {"id": "hiphop", "label_kr": "힙합", "label_en": "Hip-hop",
     "suno_tags": "hip hop, hard hitting beats, 808 bass, trap hi-hats, urban flow, street energy, confident swagger",
     "instrumental": False, "bpm_range": "85-140"},
    # ── 장소 BGM (#52-D) — 매장·공간 배경음악. 전부 연주(instrumental). ──
    {"id": "hotel_lobby", "label_kr": "호텔 로비", "label_en": "Hotel Lobby",
     "suno_tags": "hotel lobby, elegant piano solo, soft ambient, sophisticated, minimal, 70bpm",
     "instrumental": True, "bpm_range": "60-80"},
    {"id": "cafe_bgm", "label_kr": "카페 BGM", "label_en": "Café BGM",
     "suno_tags": "cafe background, acoustic guitar, light percussion, bossa nova, warm, easy listening",
     "instrumental": True, "bpm_range": "80-100"},
    {"id": "bar_lounge", "label_kr": "바/라운지", "label_en": "Bar Lounge",
     "suno_tags": "lounge bar, jazz piano, smooth saxophone, cocktail hour, sophisticated night",
     "instrumental": True, "bpm_range": "85-110"},
    {"id": "spa_meditation", "label_kr": "스파/명상", "label_en": "Spa & Meditation",
     "suno_tags": "spa ambient, meditation, soft synth pads, nature sounds, healing, peaceful, 50bpm",
     "instrumental": True, "bpm_range": "45-65"},
    {"id": "library_study", "label_kr": "도서관/서재", "label_en": "Library Study",
     "suno_tags": "classical piano, cello duet, library ambience, gentle, academic, refined, 65bpm",
     "instrumental": True, "bpm_range": "55-75"},
]

# 장소 BGM 장르 id(프론트 드롭다운·필터에서 "── 장소 BGM ──" 구분선 뒤에 표시).
PLACE_BGM_IDS: list[str] = ["hotel_lobby", "cafe_bgm", "bar_lounge", "spa_meditation", "library_study"]

GENRE_IDS: list[str] = [g["id"] for g in GENRES]
_BY_ID: dict[str, dict] = {g["id"]: g for g in GENRES}
DEFAULT_GENRE = "citypop"


def label_kr(genre_id: str) -> str:
    g = _BY_ID.get((genre_id or "").strip().lower())
    return g["label_kr"] if g else (genre_id or "")


# ── 분류 키워드 (KR+EN, 소문자) ────────────────────────────────────────
# 자유 텍스트(genre+situation+mood+title+slug, 또는 트렌드 키워드)에 대해
# substring 매칭한다. 옛 5분류 저장값도 잡히도록 레거시 단어를 포함한다.
# ⚠️ substring 매칭이라 너무 짧은 단어 금지("pop" 은 citypop/kpop 을 오염, "비" 는 비트 오염).
GENRE_KEYWORDS: dict[str, list[str]] = {
    "citypop": ["시티팝", "citypop", "city pop", "시티 팝", "네온", "neon"],
    "sunset_drive": ["선셋", "sunset", "석양", "노을", "드라이브", "drive", "운전", "cruise", "해질", "신스웨이브", "synthwave"],
    "morning_drive": ["모닝", "morning", "출근", "아침", "commute", "산뜻", "상쾌"],
    "cafe": ["카페", "cafe", "café", "커피", "coffee", "브런치", "brunch", "라운지", "lounge", "보사노바", "bossa", "어쿠스틱", "acoustic"],
    "jazz": ["재즈", "jazz", "색소폰", "saxophone", "스윙", "swing"],
    "ballad": ["발라드", "ballad"],
    "breakup": ["이별", "헤어", "breakup", "그리움", "눈물", "쓸쓸", "회상", "슬픔", "sad", "heartbreak", "lonely", "melancholic", "비 오는", "rainy", "빗방울"],
    "workout": ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat", "fitness", "트레이닝", "energetic", "edm", "하우스", "house"],
    "sleep_study": ["수면", "숙면", "취침", "sleep", "공부", "스터디", "study", "집중", "focus", "독서", "명상", "요가", "앰비언트", "ambient", "차분", "calm"],
    "lofi": ["로파이", "lofi", "lo-fi", "로-파이", "chill", "재즈힙합", "jazzhop", "jazz hip hop", "빈티지 비트"],
    "kpop": ["k-pop", "kpop", "케이팝", "케이 팝", "아이돌", "idol", "댄스", "dance"],
    "pop": ["팝송", "팝뮤직", "팝 뮤직", "american pop", "빌보드", "billboard", "radio hit"],
    "rnb_soul": ["r&b", "rnb", "알앤비", "소울", "soul", "네오소울", "neo soul", "펑크", "funk", "모타운", "motown", "k-r&b", "그루브", "groove"],
    "hiphop": ["힙합", "hiphop", "hip hop", "hip-hop", "랩", "rap", "트랩", "trap", "808", "비트박스"],
    # 장소 BGM(#52-D)
    "hotel_lobby": ["호텔", "hotel", "로비", "lobby", "그랜드 피아노", "고급 라운지"],
    "cafe_bgm": ["카페 bgm", "cafe bgm", "매장", "매장음악", "배경음악 카페"],
    "bar_lounge": ["바/라운지", "바·라운지", "bar lounge", "칵테일", "cocktail", "라운지 바", "lounge bar", "위스키 바", "고급 바", "무디"],
    "spa_meditation": ["스파", "spa", "명상", "meditation", "힐링", "healing", "요가 스파", "마사지"],
    "library_study": ["도서관", "library", "서재", "study room", "독서실", "클래식 피아노"],
}

# 옛 무드 키 → 신규 장르 id (수동/테스트 드롭다운 하위호환).
_MOOD_ALIASES = {"sleep": "sleep_study"}


def normalize_mood_key(key: str | None) -> str:
    k = (key or "").strip().lower()
    return _MOOD_ALIASES.get(k, k)


def classify(text: str | None) -> str | None:
    """자유 텍스트 → 가장 잘 맞는 장르 id 1개(매칭 없으면 None). 동점은 마스터 순서 우선."""
    t = (text or "").lower()
    best, best_n = None, 0
    for g in GENRES:
        n = sum(1 for k in GENRE_KEYWORDS[g["id"]] if k in t)
        if n > best_n:
            best, best_n = g["id"], n
    return best


def classify_theme(theme: dict) -> str | None:
    text = " ".join(str(theme.get(k, "")) for k in ("genre", "situation", "mood", "title_kr", "slug"))
    return classify(text)


# ── 수동/테스트 렌더 프리셋 (드롭다운 14종) ────────────────────────────
# manual/test 가 공유하는 단일 출처. genre 는 한국어 라벨(저장·표시용).
# style_prompt 는 기존 5프리셋과 동일 수준의 짧은 placeholder(본격 Suno 매핑은 #46).
PRESETS: dict[str, dict] = {
    "citypop": {
        "genre": "시티팝", "situation": "도시 야경 드라이브", "mood": "세련된", "type": "vocal",
        "title_kr": "시티팝", "tracks": ["City Lights", "Neon Drive"],
        "style_prompt": "city pop, 80s japanese funk, warm analog synth, slap bass, groovy, nostalgic",
        "lyric_tone": "네온이 흐르는 도시의 세련된 밤",
    },
    "sunset_drive": {
        "genre": "선셋 드라이브", "situation": "해질녘 드라이브", "mood": "몽환적인", "type": "instrumental",
        "title_kr": "선셋 드라이브", "tracks": ["Golden Hour", "Coastline"],
        "style_prompt": "synthwave, sunset drive, retro wave, warm pads, dreamy cruise",
        "lyric_tone": "노을 진 해안도로를 달리는 순간",
    },
    "morning_drive": {
        "genre": "모닝 드라이브", "situation": "아침 출근 드라이브", "mood": "상쾌한", "type": "vocal",
        "title_kr": "모닝 드라이브", "tracks": ["Morning Light", "Fresh Start"],
        "style_prompt": "upbeat pop, morning drive, acoustic guitar, bright synth, feel good",
        "lyric_tone": "맑은 아침의 산뜻한 출발",
    },
    "cafe": {
        "genre": "카페", "situation": "오후 카페", "mood": "잔잔한", "type": "instrumental",
        "title_kr": "카페", "tracks": ["Coffee Break", "Afternoon"],
        "style_prompt": "cafe acoustic, bossa nova, gentle guitar, warm atmosphere, relaxing",
        "lyric_tone": "햇살 드는 오후의 커피 한 잔",
    },
    "jazz": {
        "genre": "재즈", "situation": "늦은 밤 재즈바", "mood": "세련된", "type": "instrumental",
        "title_kr": "재즈", "tracks": ["Midnight Jazz", "Blue Note"],
        "style_prompt": "smooth jazz, saxophone, walking bass, brushed drums, sophisticated",
        "lyric_tone": "위스키 한 잔의 늦은 밤",
    },
    "ballad": {
        "genre": "발라드", "situation": "감성적인 밤", "mood": "애틋한", "type": "vocal",
        "title_kr": "발라드", "tracks": ["그대에게", "오래된 노래"],
        "style_prompt": "korean ballad, emotional piano, strings, heartfelt, cinematic",
        "lyric_tone": "마음을 울리는 따뜻한 고백",
    },
    "breakup": {
        "genre": "이별", "situation": "이별", "mood": "쓸쓸한", "type": "vocal",
        "title_kr": "이별", "tracks": ["비 오는 밤", "마지막 인사"],
        "style_prompt": "sad ballad, minor key, emotional piano, melancholic strings",
        "lyric_tone": "혼자 남은 비 오는 밤",
    },
    "workout": {
        "genre": "운동/동기부여", "situation": "운동", "mood": "에너지 넘치는", "type": "instrumental",
        "title_kr": "운동·동기부여", "tracks": ["Power Up", "Run Faster"],
        "style_prompt": "workout EDM, high energy, powerful bass, motivational, fast tempo",
        "lyric_tone": "한계를 넘는 순간의 자기긍정",
    },
    "sleep_study": {
        "genre": "수면/공부", "situation": "수면·공부", "mood": "차분한", "type": "instrumental",
        "title_kr": "수면·공부", "tracks": ["깊은 밤", "집중의 시간"],
        "style_prompt": "ambient study, soft piano, gentle rain, minimal, calming, deep focus",
        "lyric_tone": "고요한 밤의 몰입과 평온",
    },
    "lofi": {
        "genre": "로파이", "situation": "비 내리는 창가", "mood": "나른한", "type": "instrumental",
        "title_kr": "로파이", "tracks": ["Rainy Window", "Chill Tape"],
        "style_prompt": "lofi hip hop, vinyl crackle, jazzy piano, mellow beats, chill",
        "lyric_tone": "창밖에 비 내리는 나른한 오후",
    },
    "kpop": {
        "genre": "K-pop", "situation": "도시의 활기", "mood": "신나는", "type": "vocal",
        "title_kr": "K-pop", "tracks": ["Spark", "Lights Up"],
        "style_prompt": "kpop, catchy hook, synth pop, dance beat, bright energy",
        "lyric_tone": "심장을 뛰게 하는 후렴",
    },
    "pop": {
        "genre": "팝송", "situation": "화창한 거리", "mood": "경쾌한", "type": "vocal",
        "title_kr": "팝송", "tracks": ["Sunshine", "Good Day"],
        "style_prompt": "american pop, catchy melody, modern production, radio hit, feel good",
        "lyric_tone": "기분 좋아지는 화창한 하루",
    },
    "rnb_soul": {
        "genre": "R&B/소울", "situation": "도시의 밤", "mood": "감각적인", "type": "vocal",
        "title_kr": "R&B·소울", "tracks": ["Velvet Night", "Slow Jam"],
        "style_prompt": "neo soul, rnb groove, silky vocals, rhodes piano, slow jam",
        "lyric_tone": "은은한 조명 아래의 밀어",
    },
    "hiphop": {
        "genre": "힙합", "situation": "거리", "mood": "당당한", "type": "vocal",
        "title_kr": "힙합", "tracks": ["Concrete", "Flow State"],
        "style_prompt": "hip hop, hard hitting beats, 808 bass, trap hi-hats, confident",
        "lyric_tone": "거리에서 외치는 당당한 서사",
    },
    # 장소 BGM(#52-D) — 전부 연주(instrumental). lyric_tone 은 미사용(연주).
    "hotel_lobby": {
        "genre": "호텔 로비", "situation": "고급 호텔 로비", "mood": "우아한", "type": "instrumental",
        "title_kr": "호텔 로비", "tracks": ["Grand Lobby", "Marble Hall"],
        "style_prompt": "hotel lobby, elegant piano solo, soft ambient, sophisticated, minimal",
        "lyric_tone": "",
    },
    "cafe_bgm": {
        "genre": "카페 BGM", "situation": "카페 매장", "mood": "편안한", "type": "instrumental",
        "title_kr": "카페 BGM", "tracks": ["Open Door", "Latte Hour"],
        "style_prompt": "cafe background, acoustic guitar, light percussion, bossa nova, warm",
        "lyric_tone": "",
    },
    "bar_lounge": {
        "genre": "바/라운지", "situation": "고급 바", "mood": "무디한", "type": "instrumental",
        "title_kr": "바·라운지", "tracks": ["Cocktail Hour", "Velvet Bar"],
        "style_prompt": "lounge bar, jazz piano, smooth saxophone, cocktail hour, sophisticated night",
        "lyric_tone": "",
    },
    "spa_meditation": {
        "genre": "스파/명상", "situation": "스파·명상", "mood": "고요한", "type": "instrumental",
        "title_kr": "스파·명상", "tracks": ["Still Water", "Deep Breath"],
        "style_prompt": "spa ambient, meditation, soft synth pads, nature sounds, healing, peaceful",
        "lyric_tone": "",
    },
    "library_study": {
        "genre": "도서관/서재", "situation": "도서관·서재", "mood": "차분한", "type": "instrumental",
        "title_kr": "도서관·서재", "tracks": ["Quiet Shelf", "Reading Lamp"],
        "style_prompt": "classical piano, cello duet, library ambience, gentle, academic, refined",
        "lyric_tone": "",
    },
}


def preset(genre_id: str | None) -> dict:
    """장르 id → 프리셋(미지정/미지원은 기본값). 옛 무드 키 alias 도 해석."""
    gid = normalize_mood_key(genre_id)
    return PRESETS.get(gid, PRESETS[DEFAULT_GENRE])


# ── 장르별 Suno 고정 스타일(#46-C) ─────────────────────────────────────
def suno_config(genre_id: str | None) -> dict | None:
    """장르 id → {suno_tags, instrumental, bpm_range, style}. 없으면 None(=LLM 폴백).

    style: Suno style 에 바로 넣을 문자열(태그 + 'NN-NN BPM'). BPM 은 Suno 가 별도
    파라미터로 받지 않으므로(생성 body 는 style/title/instrumental 등) 태그 문자열에 싣는다.
    """
    g = _BY_ID.get(normalize_mood_key(genre_id))
    if not g or not g.get("suno_tags"):
        return None
    tags = g["suno_tags"]
    bpm = g.get("bpm_range") or ""
    return {
        "suno_tags": tags,
        "instrumental": bool(g.get("instrumental", True)),
        "bpm_range": bpm,
        "style": f"{tags}, {bpm} BPM" if bpm else tags,
    }
