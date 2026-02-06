FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared ./shared
COPY components ./components

ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev

ENV PYTHONUNBUFFERED=1

ENV PAGE_FETCHER_REDIS_URL=redis://redis:6379
ENV PAGE_FETCHER_KAFKA_BOOTSTRAP_SERVERS=kafka:9092

WORKDIR /app

CMD ["uv", "run", "page-fetcher"]
