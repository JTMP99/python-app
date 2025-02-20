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

# Install CPU-only version of PyTorch first to reduce complexity
RUN pip install --user --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install other requirements
RUN pip install --user --no-cache-dir -r requirements.txt

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
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O- https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /etc/apt/keyrings/google.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Chrome environment variable
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Create directory for storing captured files with appropriate permissions
RUN mkdir -p /app/captures && chown -R nobody:nogroup /app/captures

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    GUNICORN_CMD_ARGS="--bind=0.0.0.0:8080 --workers=2 --threads=4 --timeout=120"

# Switch to non-root user
USER nobody

# Expose port
EXPOSE 8080

# Use Gunicorn as the production server
CMD ["gunicorn", "run:app"]