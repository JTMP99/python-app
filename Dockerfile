###############################
# Stage 1: Builder
###############################
FROM python:3.10-slim as builder

# Install minimal build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install base requirements
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

# Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome
WORKDIR /app

# Copy Python packages and binaries
COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=run.py \
    FLASK_ENV=production \
    GUNICORN_CMD_ARGS="--bind=0.0.0.0:8080 --workers=1 --threads=2 --timeout=120 --log-level=info --error-logfile=- --access-logfile=-"

EXPOSE 8080

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Create start script
RUN echo '#!/bin/bash\n\
python -c "import sys; print(sys.path)"\n\
python -c "from run import app; print(app)"\n\
exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 2 --timeout 120 --log-level info --error-logfile - --access-logfile - "run:app"' > /app/start.sh \
    && chmod +x /app/start.sh

# Use start script
CMD ["/app/start.sh"]