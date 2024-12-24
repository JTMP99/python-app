FROM python:3.10-slim-buster

WORKDIR /app

# 1) Install basic tools + libs needed for Chrome & WebDriver
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libgbm-dev \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 2) Add Google Chrome's official repo & install the current stable version
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
 && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update \
 && apt-get install -y google-chrome-stable \
 && rm -rf /var/lib/apt/lists/*

# (Optional) Check Chrome version for debugging
RUN google-chrome --version

# 3) Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Copy your actual code
COPY . .

# 5) Expose the default Flask/Gunicorn port
EXPOSE 8080

# 6) Launch Gunicorn serving `app` from `server.py`
CMD gunicorn --bind 0.0.0.0:8080 server:app