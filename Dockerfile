FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /tmp/data && chmod -R 777 /tmp/data
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-8000}
