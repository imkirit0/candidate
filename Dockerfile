# Pinned slim base: small image, no build toolchain (all deps ship as wheels).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Run as an unprivileged user; the app never writes to disk.
RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

# Declared late so a new version only rebuilds this cheap layer.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Exec form: uvicorn is PID 1 and receives SIGTERM directly, so it stops accepting
# connections and finishes in-flight requests when the platform stops the container.
# One worker on purpose: the store is in process memory, more workers would each
# hold different data.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
