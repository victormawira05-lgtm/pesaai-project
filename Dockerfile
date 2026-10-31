FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# This line is critical for PrimeCloud
RUN mkdir -p /tmp/data

# Tell PrimeCloud how to start — must use $PORT and 0.0.0.0
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 app:app
