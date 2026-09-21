FROM python:3.12-slim

ENV TZ=America/Chicago

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/

ENV HOMEWORK_DB_PATH=/data/homework.db

VOLUME ["/data"]

EXPOSE 8000

CMD ["sh", "-c", "python -m scripts.bootstrap_admin && uvicorn app.asgi:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
