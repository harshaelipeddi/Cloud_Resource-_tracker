FROM python:3.11-slim

LABEL maintainer="Elipeddi Harshavardhan <harshaelipeddi15@gmail.com>"
LABEL description="AWS Cloud Resource Tracker"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tracker.py .

# Data volume mount point
VOLUME ["/data"]

ENV TRACKER_DB=/data/cloud_resources.db

CMD ["python", "tracker.py"]
