# syntax=docker/dockerfile:1.7
FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# uv for fast resolver / installer
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

WORKDIR /app

# deps layer
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project || uv sync --no-dev --no-install-project

# app layer
COPY . .
RUN uv sync --frozen --no-dev || uv sync --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

RUN groupadd -r app && useradd -r -g app -d /app app \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app
USER app

# The release this image is (a git tag, e.g. 1.2.0) — /api/healthz shows it.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
# The web server (migrations, roles and static files first); the worker,
# beat and slackbot override the command.
CMD ["sh", "/app/bin/start-web.sh"]
