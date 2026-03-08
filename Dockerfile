FROM python:3.11-slim

# 시스템 의존성 (sentence-transformers, pdfplumber, kss 빌드에 필요)
RUN apt-get update && apt-get install -y \
    gcc g++ build-essential \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch CPU-only 먼저 설치 (GPU 불필요, 이미지 크기 절감)
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

# 나머지 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 및 설정 복사
COPY src/ ./src/
COPY config/ ./config/

# 데이터/결과 디렉토리 생성
RUN mkdir -p collected_datas chroma_db logs

# 런타임에 마운트될 볼륨
VOLUME ["/app/collected_datas", "/app/chroma_db", "/app/logs"]

CMD ["python", "-m", "src.main", "--all"]
