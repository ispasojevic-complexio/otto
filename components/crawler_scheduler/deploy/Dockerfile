FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app

# Copy workspace metadata and sources to leverage Docker layer caching.
COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY components ./components

# Use an in-container virtual environment managed by uv.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev

ENV PYTHONUNBUFFERED=1

# Default Redis URL points at the docker-compose Redis service.
ENV CRAWLER_SCHEDULER_REDIS_URL=redis://redis:6379

WORKDIR /app

# Run the crawler scheduler entrypoint (defined in components/crawler_scheduler/pyproject.toml).
CMD ["uv", "run", "crawler-scheduler"]

