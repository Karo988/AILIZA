# AILIZA — minimales Docker-Image
# Build-Arg: MODE=core (Standard, ~120 MB) oder MODE=full (~400 MB)
ARG MODE=core

FROM python:3.11-slim AS base
WORKDIR /app

# System-Deps nur was wirklich gebraucht wird
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY apps/backend/requirements-core.txt requirements-core.txt
COPY apps/backend/requirements-full.txt requirements-full.txt

ARG MODE
RUN pip install --no-cache-dir -r requirements-${MODE}.txt \
    && if [ "$MODE" = "full" ]; then python -m spacy download de_core_news_sm; fi

COPY apps/backend/ ./

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
