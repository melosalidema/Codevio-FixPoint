# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 - build the React SPA
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - Python runtime serving the API and the built SPA
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system fixpoint && adduser --system --ingroup fixpoint fixpoint

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /ui/dist ./static

ENV FIXPOINT_STATIC_DIR=/app/static

RUN chmod +x ./start.sh && chown -R fixpoint:fixpoint /app
USER fixpoint

EXPOSE 8000

# The platform provides $PORT; bind to it (default 8000 locally).
CMD ["./start.sh"]
