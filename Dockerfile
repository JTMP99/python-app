FROM python:3.10-slim

# Install minimal dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python packages
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
    FLASK_ENV=production

# Create start script with debugging
RUN echo '#!/bin/bash\n\
echo "Current directory:"\n\
pwd\n\
echo "Directory contents:"\n\
ls -la\n\
echo "Python path:"\n\
python -c "import sys; print(sys.path)"\n\
echo "Starting application..."\n\
exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 run:app\n' > /app/start.sh \
    && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]