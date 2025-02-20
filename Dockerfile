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
# Stage 2: Python Dependencies
###############################
FROM base as python-deps

# Copy requirements
COPY requirements.txt .

# Install basic Flask dependencies first
RUN pip install --no-cache-dir \
    Flask==2.2.2 \
    gunicorn==20.1.0 \
    requests==2.28.2

# Install scraping dependencies
RUN pip install --no-cache-dir \
    beautifulsoup4==4.11.1 \
    selenium==4.10.0 \
    webdriver-manager==3.8.6

# Install ML dependencies separately
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir openai-whisper==20230314

###############################
# Stage 3: Final Stage
###############################
FROM base

# Copy Python packages from dependencies stage
COPY --from=python-deps /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=python-deps /usr/local/bin/ /usr/local/bin/

# Set working directory
WORKDIR /app

# Copy application code
COPY . .

# Create captures directory
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=server.py \
    FLASK_ENV=production

# Create start script with debugging
RUN echo '#!/bin/bash\n\
echo "Current directory:"\n\
pwd\n\
echo "Directory contents:"\n\
ls -la\n\
echo "Python path:"\n\
python -c "import sys; print(sys.path)"\n\
echo "Testing imports..."\n\
python -c "from app import create_app; print(\"✓ App imports successfully\")"\n\
echo "Starting application..."\n\
exec gunicorn "server:app" --bind 0.0.0.0:$PORT --workers 1 --threads 2 --log-level debug --timeout 120\n' > /app/start.sh \
    && chmod +x /app/start.sh

# Expose port
EXPOSE 8080

# Start the application
CMD ["/app/start.sh"]