FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=5000 \
    HOST=0.0.0.0 \
    WAREHOUSE_URL="http://warehouse-service:5000/inventory" \
    PASS_PROBABILITY="0.90" \
    SIMULATE_DELAY_SEC="1.0"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Startet den Webserver
CMD ["python", "app.py"]
