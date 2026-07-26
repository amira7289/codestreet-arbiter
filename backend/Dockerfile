FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests

# SQLite on most free tiers sits on an ephemeral disk, so the database is rebuilt from
# the seed on boot. Point DATABASE_PATH at a mounted volume to make it durable.
ENV DATABASE_PATH=/data/disputes.db
VOLUME /data

EXPOSE 8000
CMD ["sh", "-c", "python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
