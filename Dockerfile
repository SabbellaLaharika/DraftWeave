FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for lxml and web fetching
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Create directory for persistent SQLite database
RUN mkdir -p /app/data

# Run application
CMD ["python", "-m", "app.main"]
