# Stage 1: Build the React frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Set up the Python backend
FROM python:3.12-slim
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy planilhas de escala (necessarias em producao)
COPY data/ ./data/

# Copy frontend build output from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Expose the port Railway provides
EXPOSE ${PORT:-8080}

# Timeout 300s para suportar iteracao sobre 100+ planos por requisicao
CMD ["sh", "-c", "cd backend && gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --timeout 300 --workers 2"]
