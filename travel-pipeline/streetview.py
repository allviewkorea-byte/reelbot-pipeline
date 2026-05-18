import requests
from pathlib import Path
from config import Config, BangkokSpot

STREET_VIEW_BASE = "https://maps.googleapis.com/maps/api/streetview"

def capture_street_view(spot: BangkokSpot, config: Config) -> Path:
    """
    Google Street View Static API로 관광지 배경 이미지 캡처.
    세로형(1080x1920) 비율에 맞게 캡처.
    """
    print(f"  [streetview] {spot.name_ko} 배경 캡처 중...")

    params = {
        "size": "1080x1920",
        "location": f"{spot.lat},{spot.lng}",
        "heading": spot.heading,
        "pitch": spot.pitch,
        "fov": 90,
        "key": config.google_street_view_key,
        "return_error_code": "true",
    }

    response = requests.get(STREET_VIEW_BASE, params=params, timeout=30)
    response.raise_for_status()

    # Street View 이미지가 없을 경우 (회색 이미지) 대비 확인
    if response.headers.get("X-VPM-Error-Code"):
        raise RuntimeError(f"{spot.name_ko} Street View 이미지를 찾을 수 없습니다.")

    out_path = Path(config.images_dir) / f"{spot.id}_streetview.jpg"
    out_path.write_bytes(response.content)

    print(f"  [streetview] 저장 완료: {out_path}")
    return out_path


def check_street_view_availability(spot: BangkokSpot, config: Config) -> bool:
    """Street View 이미지 존재 여부 메타데이터로 확인."""
    meta_url = f"{STREET_VIEW_BASE}/metadata"
    params = {
        "location": f"{spot.lat},{spot.lng}",
        "key": config.google_street_view_key,
    }
    resp = requests.get(meta_url, params=params, timeout=10)
    data = resp.json()
    return data.get("status") == "OK"
