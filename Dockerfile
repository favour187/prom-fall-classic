# --- web build stage -------------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web ./
RUN npm run build

# --- runtime stage ---------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
ENV ENVIRONMENT=production \
    DATA_DIR=/app/data \
    DATABASE_URL=sqlite:////app/data/app.db \
    STATIC_DIR=/app/web/dist
COPY --from=web /web/dist ./web/dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
