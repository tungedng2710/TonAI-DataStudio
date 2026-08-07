FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends --yes git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock

COPY pyproject.toml README.md alembic.ini ./
COPY migrations ./migrations
COPY apps/api ./apps/api
RUN python -m pip install --no-cache-dir --no-deps .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn data_studio_api.main:app --host 0.0.0.0 --port 8000"]
