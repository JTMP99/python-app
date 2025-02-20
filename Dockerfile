# Use Python 3.10 slim image
FROM python:3.10-slim

# Install system dependencies and additional libraries required by Chrome
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    gnupg2 \
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
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable for Chrome binary location
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create logs directory
RUN mkdir -p logs && chmod 777 logs

# Copy application code
COPY . .

# Create non-root user and adjust permissions
RUN useradd -m appuser \
    && chown -R appuser:appuser /app

# (Optional) Set Chrome options environment variable if needed by your app
ENV CHROME_OPTIONS="--headless --disable-gpu --no-sandbox --disable-dev-shm-usage"

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Run with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "server:app"]
