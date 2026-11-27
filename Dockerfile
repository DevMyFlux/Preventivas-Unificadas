# Stage 1: Build React frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production
WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Roda sem privilégios. backend/data é gravável só para o SQLite de contingência
# (produção deve definir DATABASE_URL ou CLOUD_SQL_* — ver README).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app/backend/data
USER appuser

EXPOSE ${PORT:-8080}
CMD ["sh", "-c", "cd /app/backend && gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --timeout 300 --workers 2 --threads 4 --worker-class gthread"]
