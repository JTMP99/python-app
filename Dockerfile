# Start from a lightweight Python base
FROM python:3.10-slim-buster

# Set the working directory
WORKDIR /app

# Install system dependencies for Chrome/Chromium
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

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose port 8080 for Flask
EXPOSE 8080

# Finally, run the app via Gunicorn, pointing to server:app
CMD gunicorn --bind 0.0.0.0:8080 server:app