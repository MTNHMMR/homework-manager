FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY scripts/ scripts/

ENV HOMEWORK_DB_PATH=/data/homework.db

VOLUME ["/data"]

EXPOSE 8000

CMD ["sh", "-c", "python scripts/bootstrap_admin.py && uvicorn app.asgi:app --host 0.0.0.0 --port 8000"]
