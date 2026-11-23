FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INSIGHTFACE_HOME=/data/models \
    AOSU_FACE_DATA_DIR=/data \
    AOSU_FACE_MODEL=buffalo_sc \
    AOSU_FACE_API_KEY=aosu-local-key \
    OMP_NUM_THREADS=2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

VOLUME ["/data"]
EXPOSE 8100

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
