FROM python:3.11-slim

WORKDIR /app

# FFmpeg for audio processing + curl for Deno install
RUN apt-get update && apt-get install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/* && ffmpeg -version

# Deno JS runtime — required by yt-dlp 2026.6+ for YouTube extraction
RUN curl -fsSL https://deno.land/install.sh | sh && \
    ln -s /root/.deno/bin/deno /usr/local/bin/deno && \
    deno --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD honcho start -f Procfile
