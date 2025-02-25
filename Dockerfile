FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    xvfb \
    x11-apps \
    alsa-utils \
    pulseaudio \
    libnss3 \
    libgconf-2-4 \
    chromium \
    chromium-driver \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create captures directory (and logs, as per config.py)
RUN mkdir -p /app/captures && chmod 777 /app/captures
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=run.py \
    FLASK_DEBUG=0 \
    GOOGLE_CHROME_BIN=/usr/bin/chromium \
    DISPLAY=:99 \
    DEBUG=False

# Use environment variables from .env file if it exists
RUN if [ -f .env ]; then export $(cat .env | grep -v '^#' | xargs); fi

# Start Xvfb virtual display (in the background)
RUN Xvfb :99 -screen 0 1920x1080x24 &

EXPOSE 8080

# Run database setup script first, then start gunicorn

# CMD python setup_db.py && \
#    gunicorn --bind "0.0.0.0:8080" \

CMD gunicorn --bind "0.0.0.0:8080" \
    --workers "1" \
    --threads "2" \
    --timeout "120" \
    --access-logfile "-" \
    --error-logfile "-" \
    --log-level "debug" \
    "run:app"