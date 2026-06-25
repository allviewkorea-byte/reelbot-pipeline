import os
from dataclasses import dataclass, field
from typing import List

# 리포 루트 (이 파일은 travel-pipeline/ 아래에 있고 public/ 은 루트에 있음)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Claude(Anthropic) 모델 — 전 백엔드 공통 기본(비용 절감: Haiku). env CLAUDE_MODEL 로 한 곳에서
# 오버라이드 가능(Railway 등). 개별 서비스의 MUSIC_*_MODEL env 가 있으면 그쪽이 우선.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# 기본 캐릭터: 김이안 (char_1779198264788) — 콘티 reference 일관성 유지용
DEFAULT_CHARACTER_ID = "char_1779198264788"
_DEFAULT_CHARACTER_FRONT = os.path.join(
    _PROJECT_ROOT, "public", "character-seeds", DEFAULT_CHARACTER_ID, "front.png"
)

@dataclass
class BangkokSpot:
    id: str
    name_ko: str
    name_en: str
    description_ko: str
    lat: float
    lng: float
    heading: int = 0
    pitch: int = 0

BANGKOK_SPOTS: List[BangkokSpot] = [
    BangkokSpot(id="wat_arun", name_ko="왓아룬", name_en="Wat Arun",
        description_ko="새벽의 사원이라 불리는 왓아룬.", lat=13.7437, lng=100.4888, heading=90, pitch=10),
    BangkokSpot(id="grand_palace", name_ko="왕궁", name_en="Grand Palace",
        description_ko="태국 왕실의 심장, 왕궁.", lat=13.7500, lng=100.4913, heading=180, pitch=5),
    BangkokSpot(id="khao_san", name_ko="카오산로드", name_en="Khao San Road",
        description_ko="방콕의 대표 배낭여행자 거리.", lat=13.7588, lng=100.4977, heading=270, pitch=0),
    BangkokSpot(id="asiatique", name_ko="아시아티크", name_en="Asiatique",
        description_ko="강변의 야외 쇼핑몰, 아시아티크.", lat=13.7197, lng=100.5131, heading=0, pitch=5),
    BangkokSpot(id="siam_square", name_ko="씨암스퀘어", name_en="Siam Square",
        description_ko="방콕 최신 트렌드의 중심.", lat=13.7466, lng=100.5338, heading=135, pitch=0),
]

@dataclass
class Config:
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    google_street_view_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_STREET_VIEW_KEY", ""))
    seedance_api_key: str = field(default_factory=lambda: os.environ.get("SEEDANCE_API_KEY", ""))
    kie_api_key: str = field(default_factory=lambda: os.environ.get("KIE_API_KEY", ""))
    kie_access_key: str = field(default_factory=lambda: os.environ.get("KIE_ACCESS_KEY", ""))
    kie_secret_key: str = field(default_factory=lambda: os.environ.get("KIE_SECRET_KEY", ""))
    youtube_client_secrets_file: str = field(
        default_factory=lambda: os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json"))

    character_prompt: str = (
        "A stylish Korean woman in her mid-20s wearing trendy street fashion: "
        "oversized vintage denim jacket, wide-leg cargo pants, chunky sneakers, "
        "mini crossbody bag, silver accessories. Natural makeup, straight black hair "
        "with subtle highlights. Confident and friendly expression. "
        "Full body shot, urban travel vibe. High quality, photorealistic."
    )
    character_library_front: str = field(
        default_factory=lambda: os.environ.get(
            "CHARACTER_LIBRARY_FRONT",
            _DEFAULT_CHARACTER_FRONT
        )
    )

    video_width: int = 1080
    video_height: int = 1920
    video_fps: int = 30
    video_duration_per_spot: int = 15

    output_dir: str = "output"
    images_dir: str = "output/images"
    videos_dir: str = "output/videos"
    audio_dir: str = "output/audio"
    final_dir: str = "output/final"

    tts_voice: str = "ko-KR-SunHiNeural"
    tts_rate: str = "+10%"

    youtube_category_id: str = "19"
    youtube_tags: List[str] = field(default_factory=lambda: [
        "방콕여행", "태국여행", "Bangkok", "Thailand",
        "왓아룬", "왕궁", "카오산로드", "아시아티크", "씨암스퀘어",
        "AI여행", "여행브이로그", "혼자여행"
    ])

    def validate(self):
        missing = []
        if not self.openai_api_key: missing.append("OPENAI_API_KEY")
        if not self.anthropic_api_key: missing.append("ANTHROPIC_API_KEY")
        if not self.google_street_view_key: missing.append("GOOGLE_STREET_VIEW_KEY")
        if not self.seedance_api_key: missing.append("SEEDANCE_API_KEY")
        if missing:
            raise EnvironmentError(f"필수 환경변수 누락: {', '.join(missing)}")