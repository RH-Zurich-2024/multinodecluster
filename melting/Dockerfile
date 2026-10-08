# ==============================================================================
# melting Service – Container-Image
# Bauen:  docker build -t melting-service:1.0.0 melting-service/
# Starten: docker run --rm -p 8003:8003 -e CASTING_SERVICE_URL=http://casting-service:8004/cast melting-service:1.0.0
# ==============================================================================

# ---------- Stage 1: Build --------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Zuerst nur die Requirements kopieren: Docker cached die Layer, solange
# sich die Abhängigkeiten nicht ändern.
COPY requirements.txt .

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: Runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Melting Service" \
      org.opencontainers.image.description="Schmelzofen-Microservice der Fabrik-Pipeline" \
      org.opencontainers.image.version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8003 \
    CASTING_SERVICE_URL="http://localhost:8004/cast" \
    LOG_LEVEL=INFO

# venv aus der Build-Stage übernehmen (enthält uvicorn[standard] inkl. uvloop)
COPY --from=builder /opt/venv /opt/venv

# Dedizierter, nicht-privilegierter Nutzer
RUN groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --chown=app:app main.py ./

USER app

EXPOSE 8003

# Container-Healthcheck: greift dieselbe URL wie die Kubernetes-Probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8003/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8003", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--access-log"]