FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ .
RUN useradd -m app && chown -R app /app
USER app
CMD uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
