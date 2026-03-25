FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY backend/requirements.txt ./requirements.txt
COPY assignments/a2/data_pipeline/requirements.txt ./a2-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r a2-requirements.txt

# Copy source
COPY backend/app/ ./app/
COPY assignments/a2/data_pipeline/ ./assignments/a2/data_pipeline/

# AWS ECS exposes the container on 8000
EXPOSE 8000

# Uvicorn with 2 workers — tune based on ECS task CPU
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
