FROM python:3.12-slim

WORKDIR /app

# Install build dependencies for libraries like psutil or faiss-cpu if compiled from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition first (better layer caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Render (and most PaaS) dynamically assigns PORT via env var; default to 8001 for local use
ENV PORT=8001

# Expose the application port
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\",\"8001\")}/admin/health')" || exit 1

# Use shell form so $PORT is expanded at runtime
CMD uvicorn app:app --host 0.0.0.0 --port $PORT
