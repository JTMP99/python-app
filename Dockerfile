###############################
# Stage 1: Base Python
###############################
FROM python:3.10-slim as base

WORKDIR /app

# Install base system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

###############################
# Stage 2: Core Dependencies
###############################
FROM base as core-deps

COPY requirements.txt .

# Install core Flask dependencies
RUN pip install --no-cache-dir \
    Flask==2.2.2 \
    gunicorn==20.1.0 \
    requests==2.28.2

###############################
# Stage 3: Streaming Dependencies
###############################
FROM core-deps as streaming-deps

# Install ML dependencies
RUN pip install --no-cache-dir \
    openai-whisper==20230314 \
    torch --index-url https://download.pytorch.org/whl/cpu

###############################
# Stage 4: Final Stage
###############################
FROM base

# Copy Python packages from dependencies stages
COPY --from=streaming-deps /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=streaming-deps /usr/local/bin/ /usr/local/bin/

WORKDIR /app

# Copy the application code
COPY app app/
COPY server.py .

# Create necessary directories
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=server.py \
    FLASK_ENV=production

# Create debug script
RUN echo '#!/bin/bash\n\
echo "=== Directory Structure ==="\n\
ls -R /app\n\
echo "=== Python Path ==="\n\
python -c "import sys; print(sys.path)"\n\
echo "=== Testing Basic Import ==="\n\
python -c "from app import create_app; print(\"✓ App imports successfully\")"\n\
echo "=== App Structure ==="\n\
python -c "from app import create_app; app = create_app(); print(app.url_map)"\n\
echo "=== Starting Application ==="\n\
exec gunicorn --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 2 \
    --timeout 120 \
    --log-level debug \
    --error-logfile - \
    --access-logfile - \
    "server:app"' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]