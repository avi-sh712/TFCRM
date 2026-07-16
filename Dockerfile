FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TALENTFORGE_STATIC_DIR=/app/talentforge/static

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY talentforge/ ./talentforge/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY --from=frontend-build /app/frontend/dist ./talentforge/static/

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn talentforge.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
