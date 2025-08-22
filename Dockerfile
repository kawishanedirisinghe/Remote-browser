# Dockerfile (recommended)
FROM mcr.microsoft.com/playwright/python:latest

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure port from Render is respected (Render provides $PORT)
ENV PORT 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
