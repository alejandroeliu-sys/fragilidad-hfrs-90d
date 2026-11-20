# Imagen reproducible del avance. 
# Nombre completo de la imagen: Se utilizó Podman en Fedora.
FROM docker.io/library/python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY sql/ sql/
COPY tests/ tests/
COPY referencias/ referencias/

ENV PYTHONPATH=src

CMD ["pytest", "-q"]
