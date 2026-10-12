FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt requirements-connectors.txt ./
RUN pip install --no-cache-dir -r requirements-connectors.txt
COPY backend/ ./backend/
COPY connectors/ ./connectors/
COPY scripts/add_college.py ./scripts/add_college.py
COPY scripts/__init__.py ./scripts/__init__.py
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN useradd --create-home --uid 10001 pulseiq
USER pulseiq
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn backend.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*' --no-access-log"]
