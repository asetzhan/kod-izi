FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# cppcheck for static analysis (ФТ-32); clang-tidy comes from the pip package.
# poppler and Tesseract with Kazakh and Russian data for scanned books (ФТ-37).
RUN apt-get update \
    && apt-get install -y --no-install-recommends cppcheck poppler-utils \
       tesseract-ocr tesseract-ocr-kaz tesseract-ocr-rus \
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

# Code-DKT (ФТ-40, Q-19): the app plus PyTorch for CPU, installed at build time from the
# PyTorch index only (no second index, so no package can be swapped in from elsewhere).
FROM app AS ml
USER root
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1"
USER app

# Code similarity worker (ФТ-30): the same app plus a JRE and JPlag, checked by its hash.
FROM app AS analyzer
USER root
ARG JPLAG_VERSION=6.3.0
ARG JPLAG_SHA256=5f2c21e8b88ed77134effcb3a5a3ab13d188f6a3e16d401387f7479e92db9aa2
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless curl \
    && mkdir -p /opt/jplag \
    && curl -fsSL -o /opt/jplag/jplag.jar \
       "https://github.com/jplag/JPlag/releases/download/v${JPLAG_VERSION}/jplag-${JPLAG_VERSION}-jar-with-dependencies.jar" \
    && echo "${JPLAG_SHA256}  /opt/jplag/jplag.jar" | sha256sum -c - \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
USER app
CMD ["sh", "-c", "rq worker --url \"$REDIS_URL\" analysis"]
