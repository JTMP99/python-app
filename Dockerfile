FROM python:3.10-slim

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install only the core dependencies
RUN pip install --no-cache-dir \
    Flask==2.2.2 \
    gunicorn==20.1.0 \
    requests==2.28.2 \
    beautifulsoup4==4.11.1 \
    selenium==4.10.0 \
    webdriver-manager==3.8.6

# Copy application code
COPY app app/
COPY run.py .

# Create captures directory
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=run.py \
    FLASK_ENV=production

# Debug script
RUN echo '#!/bin/bash\n\
echo "=== Directory Structure ==="\n\
ls -R /app\n\
echo "=== Starting Application ==="\n\
exec gunicorn "run:app" \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 2 \
    --timeout 120 \
    --log-level debug \
    --error-logfile - \
    --access-logfile -' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]