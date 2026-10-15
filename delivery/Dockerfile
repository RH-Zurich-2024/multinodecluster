FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY delivery.py ./delivery.py
COPY index.html ./index.html
RUN pip install --no-cache-dir "psycopg2-binary>=2.9.9"

EXPOSE 80

CMD ["python3", "delivery.py"]
