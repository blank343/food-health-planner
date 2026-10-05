# Build-Kontext ist die PROJEKTWURZEL (siehe deploy/docker-compose.yml):
#   docker build -f backend/Dockerfile -t foodhealth .

# --- Stufe 1: Web-Oberfläche bauen -------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN node node_modules/typescript/bin/tsc --noEmit && node node_modules/vite/bin/vite.js build

# --- Stufe 2: Backend + gebaute Oberfläche ---------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1     FHP_WEB_DIR=/app/web

WORKDIR /app

# Nicht-root-Benutzer
RUN useradd --system --create-home --uid 10001 app

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN pip install .
COPY --from=web /web/dist /app/web

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
