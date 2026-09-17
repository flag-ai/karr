# ---- Frontend builder ----
FROM node:22-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ---- Python builder ----
FROM python:3.12-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir poetry==2.* \
    && poetry config virtualenvs.in-project true
WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --no-interaction --no-ansi --without dev --no-root
COPY src/ src/
COPY --from=frontend-builder /frontend/dist src/karr/web/static
RUN poetry install --no-interaction --no-ansi --without dev

# ---- Runtime ----
FROM python:3.12-slim
ARG VERSION=dev  # informational: the package version comes from pyproject; kept for image labels
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
RUN groupadd --gid 1000 karr && useradd --uid 1000 --gid karr --create-home karr
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY --from=builder /app/src src
COPY pyproject.toml ./
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FLAG_BUILD_COMMIT=$COMMIT \
    FLAG_BUILD_DATE=$BUILD_DATE \
    LISTEN_ADDR=:8080
LABEL org.opencontainers.image.version=$VERSION org.opencontainers.image.revision=$COMMIT org.opencontainers.image.created=$BUILD_DATE
USER karr
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
ENTRYPOINT ["karr"]
CMD ["serve"]
