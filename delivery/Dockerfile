FROM python:3.13-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY delivery.py ./delivery.py
COPY index.html ./index.html

EXPOSE 80

CMD ["python3", "delivery.py"]
