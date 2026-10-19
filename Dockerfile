# Hosting image: admin and license API only.
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra admin --no-install-project

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/app/.venv/bin:$PATH" \
    PORT=3000 \
    LIVE_STUDIO_LICENSE_DATA=/app/data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/license_server /app/src/license_server
RUN mkdir -p /app/data
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','3000')+'/health',timeout=3)" || exit 1
CMD ["python", "-m", "license_server.hosting"]
