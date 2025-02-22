FROM python:3.10-slim

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create captures directory
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    FLASK_APP=run.py \
    FLASK_ENV=production \
    GOOGLE_CHROME_BIN=/usr/bin/chromium \
    DEBUG=False \
    SECRET_KEY="your-secret-key-change-in-production"

EXPOSE 8080

# Use simpler CMD to help with debugging
CMD ["gunicorn", "--bind", "0.0.0.0:8080", \
     "--workers", "1", \
     "--threads", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "debug", \
     "run:app"]