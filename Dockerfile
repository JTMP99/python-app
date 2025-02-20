###############################
# Stage 1: Builder
###############################
FROM python:3.10-slim as builder

# Install build tools and dependencies needed for pip installs.
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

# Copy only the requirements first, so this layer is cached.
COPY requirements.txt .

# Install Python dependencies into a local directory.
RUN pip install --user --no-cache-dir -r requirements.txt

###############################
# Stage 2: Final Image
###############################
FROM python:3.10-slim

# Install runtime dependencies.
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
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome.
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable for Chrome binary.
ENV GOOGLE_CHROME_BIN=/usr/bin/google-chrome

WORKDIR /app

# Copy installed Python packages from the builder stage.
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy the application code.
COPY . .

# Expose port 8080.
EXPOSE 8080

# Run the app using Gunicorn with your application factory.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:create_app()"]
