FROM python:3.9-slim-bullseye

# Install system dependencies including DSSP and build tools for BioPython
RUN apt-get update && apt-get install -y \
    dssp \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "3", "--timeout", "300", "app:app"]
