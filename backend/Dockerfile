FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Ensure we use the proper python environment
ENV PYTHONUNBUFFERED=1

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source code
COPY . /app

# Ensure python path includes /app so module imports work
ENV PYTHONPATH=/app

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
