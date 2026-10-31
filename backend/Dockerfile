FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# cppcheck for static analysis (ФТ-32); clang-tidy comes from the pip package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cppcheck \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Dependencies first so code changes do not invalidate this layer.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install -e ".[dev]" && rm -rf app

COPY . .
RUN chown -R app:app /app
USER app

EXPOSE 8000
# Proxy headers are trusted only where the proxy address is known (infra/docker-compose.yml).
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
