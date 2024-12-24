FROM python:3.10-slim-buster

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libxss1 \
    libappindicator3-1 \
    libgbm-dev \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    chromium \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD gunicorn --bind 0.0.0.0:8080 server:app