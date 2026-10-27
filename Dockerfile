# La versión de la imagen DEBE coincidir con la de playwright en requirements.txt
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
# Un solo worker: la cola vive en memoria
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]