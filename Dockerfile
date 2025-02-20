###############################
# Stage 1: Builder
###############################
FROM python:3.10-slim as builder

# Install minimal build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and modify for minimal install
COPY requirements.txt .

# Split package installation to manage memory better
RUN pip install --no-cache-dir gunicorn==20.1.0 \
    Flask==2.2.2 \
    requests==2.28.2 \
    beautifulsoup4==4.11.1 \
    selenium==4.10.0 \
    webdriver-manager==3.8.6

# Install ML packages separately
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu 
RUN pip install --no-cache-dir openai-whisper==20230314

###############################
# Stage 2: Runtime
###############################
FROM python:3.10-slim

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    gnupg2 \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-cache-dir google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome
WORKDIR /app

# Copy Python packages and binaries
COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY . .

# Create captures directory
RUN mkdir -p /app/captures && chmod 777 /app/captures

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2", "run:app"]