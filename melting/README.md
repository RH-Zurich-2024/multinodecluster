# Smelting Service

Microservice einer containerisierten Fabrik-Pipeline. Der Service nimmt
Materialchargen entgegen, simuliert den Schmelzvorgang und reicht das
angereicherte Datenpaket per HTTP an den **Casting Service** weiter.

```
Client ──POST /smelt──▶ Smelting Service ──POST /cast──▶ Casting Service
                           (Port 8003)        (Port 8004)
```

## Ordnerstruktur

```
multinodecluster/
└── smelting-service/
    ├── main.py               # FastAPI-App, Schmelzlogik, HTTP-Weiterleitung
    ├── requirements.txt      # Laufzeitabhängigkeiten
    ├── Dockerfile            # Multi-Stage-Build, exponiert Port 8003
    ├── .dockerignore        # Build-Kontext auf das Nötige beschränken
    └── README.md             # dieses Dokument
```

## Konfiguration

Alle Werte werden über Umgebungsvariablen gesetzt (Kubernetes: `env:` im
Deployment bzw. `configMapRef`/`secretKeyRef`).

| Variable                  | Default                            | Beschreibung                                    |
| ------------------------- | ---------------------------------- | ----------------------------------------------- |
| `CASTING_SERVICE_URL`     | `http://localhost:8004/cast`       | Ziel-URL des Casting Service                    |
| `SMELT_DURATION_SECONDS`  | `3`                                | Simulierte Schmelzdauer (Default: 3 s)          |
| `MELT_TEMPERATURE_CELSIUS`| `1450`                             | Temperatur der Schmelze                         |
| `CASTING_TIMEOUT_SECONDS` | `10`                               | Timeout für den Downstream-Call                 |
| `LOG_LEVEL`               | `INFO`                             | Logstufe                                        |
| `HOST` / `PORT`           | `0.0.0.0` / `8003`                 | Bind-Adresse (nur für `python main.py`)         |

## Lokal starten

### Variante A: direkt mit Python (schnellster Weg)

```bash
cd smelting-service

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export CASTING_SERVICE_URL="http://localhost:8004/cast"
export SMELT_DURATION_SECONDS="3"

python main.py
# oder: uvicorn main:app --host 0.0.0.0 --port 8003 --reload
```

### Variante B: als Container

```bash
docker build -t smelting-service:1.0.0 smelting-service/
docker run --rm -p 8003:8003 \
  -e CASTING_SERVICE_URL="http://localhost:8004/cast" \
  smelting-service:1.0.0
```

## Testen mit curl

Der Service erwartet den **Casting Service** unter `CASTING_SERVICE_URL`.
Damit der lokale Test ohne den echten Downstream-Service funktioniert,
genügt ein minimaler Dummy auf Port 8004. Wichtig ist `ThreadingHTTPServer` –
ein einfaches `HTTPServer` bearbeitet nur einen Request zur Zeit und ließe
parallele Aufträge in Timeouts laufen:

```bash
# Terminal 1 – Dummy Casting Service
python3 - <<'PY'
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        payload = json.loads(self.rfile.read(n))
        print("[casting] empfangen:", json.dumps(payload, ensure_ascii=False), flush=True)
        body = json.dumps({"status": "cast", "received": payload}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

ThreadingHTTPServer(("0.0.0.0", 8004), H).serve_forever()
PY
```

```bash
# Terminal 2 – Smelting Service
cd smelting-service && python main.py
```

```bash
# Terminal 3 – Health-Check
curl -s http://localhost:8003/health | jq
# {"status":"healthy","service":"smelting-service","version":"1.0.0","uptime_s":12.34}

# Schmelzauftrag auslösen (dauert ~3 s)
curl -s -X POST http://localhost:8003/smelt \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "MET-101", "material": "Eisen", "weight_kg": 500, "location": "furnace"}' | jq
```

Erwartete Antwort:

```json
{
  "batch_id": "MET-101",
  "material": "Eisen",
  "weight_kg": 500.0,
  "location": "furnace",
  "status": "liquid",
  "temp_celsius": 1450,
  "casting_service_status": 200,
  "casting_response": { "status": "cast" },
  "processing_time_s": 3.012
}
```

Schneller Test ohne 3 s Wartezeit:

```bash
SMELT_DURATION_SECONDS=0.2 python main.py &
curl -s -X POST http://localhost:8003/smelt \
  -H "Content-Type: application/json" \
  -d '{"batch_id":"MET-102","material":"Aluminium","weight_kg":250,"location":"furnace"}' | jq
```

### Nebenläufigkeit prüfen

Das Warten auf die Schmelzdauer blockiert den Event-Loop nicht – mehrere
Aufträge laufen daher parallel statt hintereinander:

```bash
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w "job$i: HTTP %{http_code} in %{time_total}s\n" \
    -X POST http://localhost:8003/smelt -H "Content-Type: application/json" \
    -d "{\"batch_id\":\"MET-30$i\",\"material\":\"Kupfer\",\"weight_kg\":100,\"location\":\"furnace\"}" &
done
wait
# alle 5 melden ~3s, Gesamtzeit ~3s (seriell wären es ~15s)
```

Interaktive API-Doku: <http://localhost:8003/docs>

## Fehlerverhalten

| Situation                                   | HTTP-Status der Antwort |
| ------------------------------------------- | ----------------------- |
| Validierung fehlgeschlagen (z. B. `weight_kg <= 0`) | 422              |
| Casting Service nicht erreichbar            | 502                     |
| Casting Service antwortet nicht rechtzeitig | 504                     |
| Casting Service liefert 5xx                  | 502                     |
| Casting Service lehnt Auftrag ab (4xx)       | wird durchgereicht      |
| Unerwarteter interner Fehler                | 500                     |

## Kubernetes

Beispiel-Auszug aus dem Deployment (`smelting-service` auf Port 8003):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smelting-service
spec:
  replicas: 2
  selector:
    matchLabels: { app: smelting-service }
  template:
    metadata:
      labels: { app: smelting-service }
    spec:
      containers:
        - name: smelting-service
          image: smelting-service:1.0.0
          ports:
            - containerPort: 8003
          env:
            # In-Cluster-DNS-Name des Casting Service
            - name: CASTING_SERVICE_URL
              value: "http://casting-service:8004/cast"
            - name: LOG_LEVEL
              value: "INFO"
          readinessProbe:
            httpGet: { path: /health, port: 8003 }
            initialDelaySeconds: 3
            periodSeconds: 10
          livenessProbe:
            httpGet: { path: /health, port: 8003 }
            initialDelaySeconds: 10
            periodSeconds: 20
          resources:
            requests: { cpu: 50m, memory: 64Mi }
            limits:   { cpu: 500m, memory: 256Mi }
---
apiVersion: v1
kind: Service
metadata:
  name: smelting-service
spec:
  selector: { app: smelting-service }
  ports:
    - port: 8003
      targetPort: 8003
```

Hinweis zur Skalierung: `uvicorn` läuft mit 2 Worker-Prozessen. Da jeder
Worker einen eigenen HTTP-Connection-Pool hält, sollte die Workerzahl zur
CPU-Allokation des Pods passen ( Faustregel: `2 * CPU + 1`).