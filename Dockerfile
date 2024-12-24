FROM python:3.10-slim-buster

WORKDIR /app

# Install system tools and libraries needed by Chrome & Selenium
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

# Add Google Chrome's official repository and install Chrome 114
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
 && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update \
 && apt-get install -y google-chrome-stable=114.0.5735.90-1 \
 && rm -rf /var/lib/apt/lists/*

# Confirm Chrome is indeed version 114
RUN google-chrome --version

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your source code
COPY . .

EXPOSE 8080

# Run Gunicorn to serve your Flask app (server.py, app=Flask(__name__))
CMD gunicorn --bind 0.0.0.0:8080 server:app