# Imagen mínima: menos superficie que mantener y que actualizar.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SEAL_DB=/data/seal.db

WORKDIR /app

# Las dependencias primero: así el caché de capas no se invalida al tocar código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /data es el punto de montaje del volumen persistente. Si no se monta nada,
# la base de datos se pierde en cada redespliegue: ver fly.toml.
RUN mkdir -p /data

EXPOSE 8080
CMD ["./start.sh"]
