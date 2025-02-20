###############################
# Stage 1: Builder
###############################
FROM python:3.10-slim as builder

# Install build tools and dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    python3-dev \
    wget \
    curl \
    unzip \
    gnupg2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install packages globally in the builder stage instead of --user
RUN pip install --no-cache-dir -r requirements.txt

###############################
# Stage 2: Runtime
###############################
FROM python:3.10-slim

# Install runtime dependencies and cleanup in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    unzip \
    gnupg2 \
    ffmpeg \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Chrome environment variable
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome

WORKDIR /app

# Copy installed Python packages from builder - now copying from global site-packages
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create directory for storing captured files
RUN mkdir -p /app/captures && chmod 777 /app/captures

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Use Gunicorn as the production server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "run:app"]