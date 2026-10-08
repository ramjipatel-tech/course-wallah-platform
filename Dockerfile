# Course Wallah Multi-Service Production Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Install system dependencies including FFmpeg and fonts for watermarking
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Ensure storage and session directories exist
RUN mkdir -p /app/data /app/temp /app/downloads /app/assets /app/data/thumbnails /app/data/sessions

# Expose port
EXPOSE 8000

# Start unified supervisor (runs FastAPI Web + Telegram Bot + Background Worker)
CMD ["python", "start.py"]
