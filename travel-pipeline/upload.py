import os
import datetime
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import Config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = "youtube_token.json"


def _get_youtube_service(config: Config):
    """OAuth2 인증 후 YouTube API 서비스 객체 반환."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.youtube_client_secrets_file, SCOPES
            )
            creds = flow.run_local_server(port=0)

        Path(TOKEN_FILE).write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(video_path: Path, config: Config) -> str:
    """
    YouTube Data API v3로 영상 업로드.
    업로드된 영상의 video_id 반환.
    """
    print(f"  [upload] YouTube 업로드 시작: {video_path.name}")

    youtube = _get_youtube_service(config)
    today = datetime.date.today().strftime("%Y.%m.%d")

    title = f"🇹🇭 방콕 여행 브이로그 | 왓아룬부터 씨암스퀘어까지 | {today}"
    description = (
        "안녕하세요! 오늘은 방콕의 핫플을 함께 투어해볼게요 🌟\n\n"
        "📍 이번 영상 코스\n"
        "00:00 인트로\n"
        "00:20 왓아룬 (새벽의 사원)\n"
        "00:35 왕궁\n"
        "00:50 카오산로드\n"
        "01:05 아시아티크\n"
        "01:20 씨암스퀘어\n\n"
        "#방콕여행 #태국여행 #Bangkok #여행브이로그 #혼자여행 #AI여행"
    )

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": config.youtube_tags,
            "categoryId": config.youtube_category_id,
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": "private",  # 검토 후 수동으로 public 전환
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10,  # 10MB 청크
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"  [upload] 업로드 진행: {progress}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"  [upload] 업로드 완료!")
    print(f"  [upload] 영상 URL: {video_url}")

    return video_id
