FROM python:3.11-slim

# 시스템 패키지: ffmpeg/폰트(기존) + Node 22 + Chromium(Remotion 렌더용) + Chromium 시스템 libs.
# Remotion 은 시스템 Chromium 을 쓴다(REMOTION_CHROMIUM_EXECUTABLE) → remotion.media 자동
# 다운로드(차단 가능)에 의존하지 않는다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg fonts-nanum fonts-noto-cjk fontconfig \
       curl ca-certificates gnupg \
       chromium \
       libnss3 libgbm1 libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
       libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
       libpango-1.0-0 libcairo2 libxshmfence1 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

ENV SUBTITLE_FONT_PATH=/usr/share/fonts/truetype/nanum/NanumGothic.ttf
# Remotion 이 쓸 시스템 Chromium 경로(자동 다운로드 회피).
ENV REMOTION_CHROMIUM_EXECUTABLE=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Remotion 의존성 설치(매니페스트 먼저 복사 → 레이어 캐시). lock 있으면 ci, 없으면 install.
COPY remotion/package.json remotion/package-lock.json* ./remotion/
RUN cd remotion \
    && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)

COPY . .

CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
