FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    WAREHOUSE_URL="http://warehouse:81/inventory" \
    PASS_PROBABILITY="0.60" \
    SIMULATE_DELAY_SEC="0.5"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Startet den Webserver
CMD ["python", "app.py"]
