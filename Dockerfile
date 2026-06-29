FROM python:3.11-slim

WORKDIR /app

# FFmpeg + curl + unzip
RUN apt-get update && apt-get install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/* && ffmpeg -version

# Rust POT provider server — generates PO tokens to bypass YouTube bot detection
RUN curl -sL https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v0.8.1/bgutil-pot-linux-x86_64 -o /usr/local/bin/bgutil-pot && \
    chmod +x /usr/local/bin/bgutil-pot && \
    bgutil-pot --version

# Deno JS runtime — required by yt-dlp 2026.6+ for YouTube extraction
RUN curl -fsSL https://deno.land/install.sh | sh && \
    ln -s /root/.deno/bin/deno /usr/local/bin/deno && \
    deno --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD honcho start -f Procfile
