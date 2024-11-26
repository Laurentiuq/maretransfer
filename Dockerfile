FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt
# Create necessary directories
RUN mkdir -p static templates audio_chunks
RUN apt-get update && apt-get install -y ffmpeg
# Copy application files
COPY static/audio-capture.js static/
COPY templates/index.html templates/
COPY app.py .

# Expose port
EXPOSE 8000

# Start the application
CMD ["python", "app.py"]

ENV PYTHONUNBUFFERED=1
