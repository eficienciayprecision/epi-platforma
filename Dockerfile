FROM python:3.11-slim

WORKDIR /app

# PYTHONUNBUFFERED=1: sin esto, los print() de la aplicacion (como el aviso
# de exito/error al enviar un email) pueden quedarse retenidos en el buffer
# de salida de Python y no aparecer en los logs de Render hasta mucho mas
# tarde (o nunca, si el contenedor no se reinicia) — un fallo de
# configuracion tipico en Docker que costo diagnosticar un problema de
# envio de email en agosto 2026 (el codigo funcionaba bien, pero su aviso
# de error no se veia en los logs).
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
