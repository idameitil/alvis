# Older image required to build BioPython
FROM python:3.9-slim-bullseye

# Install system dependencies including DSSP and build tools for BioPython.
# `rm -rf /var/lib/apt/lists/*` deletes apt's package index (only needed
# during install) in the same layer as the install, so it doesn't bloat
# the final image.
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

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "3", "--timeout", "300", "app:app"]
