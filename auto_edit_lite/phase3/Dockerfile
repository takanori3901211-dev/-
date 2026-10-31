# ビルドコンテキストは auto_edit_lite/ ディレクトリを指定すること:
#   cd auto_edit_lite && docker build -f phase3/Dockerfile -t auto-edit-lite .

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY phase3/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lite_edit.py edit_brain.py make_video.py ./
COPY phase3/cloudrun_server.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "cloudrun_server.py"]
