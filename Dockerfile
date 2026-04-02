FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Gunicorn with 1 worker (critical — APScheduler needs single process)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 "app:create_app()"
