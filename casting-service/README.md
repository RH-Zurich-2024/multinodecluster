# Service 4: Casting & Qualitätsprüfung (Gießerei & Prüfung)

Teil der 5-teiligen Fabrik-Pipeline auf dem K3s Multinode Cluster:
1. `Delivery` (Startpunkt: Nimmt Material via POST /deliver entgegen)
2. `Transport` (Logistik: 2s Simulation, ergänzt `"location": "furnace"`)
3. `Smelting` (Schmelzofen: setzt `"temp": 1450`, `"status": "liquid"`)
4. **`Casting` (DIESER SERVICE: Gießen & Qualitätsprüfung)**
   * Formt das Metall: setzt `"shape": "Barren"`
   * Führt Qualitätsprüfung durch: 90 % `PASSED`, 10 % `REJECTED`
   * Sendet fertiges Datenpaket per HTTP POST an den Lager-Service (Warehouse)
5. `Warehouse` (Endstation: Speichert in `inventory = []`, Anzeige via GET /inventory)

---

## Datenpaket-Transformation in diesem Service

**Eingang von Service 3 (Smelting):**
```json
{
  "batch_id": "MET-101",
  "material": "Eisen",
  "weight_kg": 500,
  "status": "liquid",
  "temp_celsius": 1450
}
```

**Ausgang an Service 5 (Warehouse):**
```json
{
  "batch_id": "MET-101",
  "material": "Eisen",
  "weight_kg": 500,
  "shape": "Barren",
  "quality": "PASSED"
}
```

---

## Features der Web-UI

* **Modernes Industrial Dark-Theme** (Tailwind CSS, Status-Badges, Glowing Accents)
* **Pipeline-Ablauf Übersicht**: Visueller Status der 5 Services
* **Live KPI-Metriken**:
  * Gesamt verarbeitete Batches
  * Bestanden (`PASSED` in Grün) mit Erfolgsquote
  * Abgelehnt (`REJECTED` in Rot) als Ausschuss
  * An Lager übergeben (Erfolgreiche HTTP POSTs)
* **Interaktiver Test-Simulator**:
  * Manuelles Erstellen und Absenden von Test-Batches direkt im Browser
  * Live-Fortschritt und Rückmeldung
* **Verlaufs-Tabelle**:
  * Chronologische Liste aller Prüfungen
  * Klick auf `JSON` zeigt das vollständige Datenpaket (Vorher vs. Nachher)
* **Echtzeit-Log**:
  * Terminal-Stream aller eingehenden und ausgehenden HTTP-Aufrufe
* **Laufzeit-Konfiguration**:
  * Pass-Rate (0–100 %, Standard: 90 %)
  * Ziel-URL des Warehouse-Services
  * Simulierte Gieß-/Abkühlzeit

---

## Lokaler Start

```bash
cd casting-service
pip install -r requirements.txt
python app.py
```
Öffne anschließend [http://localhost:5000](http://localhost:5000) im Browser.

---

## Docker Build & Run

```bash
cd casting-service

# Docker Image bauen
docker build -t casting-service:latest .

# Container starten
docker run -d -p 5000:5000 \
  -e WAREHOUSE_URL="http://warehouse-service:5000/inventory" \
  -e PASS_PROBABILITY="0.90" \
  --name casting-app casting-service:latest
```

---

## Deployment auf dem K3s Multinode Cluster

Die Kubernetes-Manifeste befinden sich im Ordner `k8s/`:

```bash
# Auf dem K3s Master ausführen:
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

* **Cluster-interner Zugriff für Service 3 (Smelting):**
  `http://casting-service:5000/cast`
* **Web-UI Zugriff von außen (Browser):**
  `http://<NODE_PUBLIC_IP>:30040` (über den NodePort 30040)

---

## API-Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/cast` | Pipeline-Endpunkt (wird von Service 3 Smelting aufgerufen) |
| `GET` | `/` | Web-UI Dashboard |
| `GET` | `/api/stats` | Zähler & Metriken als JSON |
| `GET` | `/api/batches` | Liste der letzten 50 verarbeiteten Batches |
| `GET` | `/api/logs` | Letzte Log-Meldungen |
| `POST` | `/api/test-batch` | Manueller Test-Trigger aus der UI |
| `POST` | `/api/config` | Aktualisieren von Pass-Rate oder Warehouse-URL |
| `GET` | `/health` | Kubernetes Health / Readiness Probe |

### Test per `curl`:

```bash
curl -X POST http://localhost:5000/cast \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "MET-101",
    "material": "Eisen",
    "weight_kg": 500,
    "status": "liquid",
    "temp_celsius": 1450
  }'
```
