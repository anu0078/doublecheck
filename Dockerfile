# Container for Google Cloud Run (also works on any Docker host).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Don't run as root inside the container
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Cloud Run tells us the port in $PORT. --no-access-log: we never log request lines.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-access-log
