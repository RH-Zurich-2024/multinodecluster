# FORGE Warehouse

Eigenständiger Warehouse-Service: FastAPI, animiertes Dashboard, In-Memory-Bestand, Docker und Kubernetes. Die anderen vier Pipeline-Services sind nicht implementiert.

## Lokal starten

Im Warehouse-Ordner:

```powershell
docker compose up --build
```

Dashboard: http://localhost:8000 · API-Dokumentation: http://localhost:8000/docs

Alternativ mit Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:ENABLE_DEMO = "true"
.venv\Scripts\python -m uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1
```

## Casting anbinden

Casting sendet HTTP POST an `http://warehouse/store` im selben Kubernetes-Namespace. `POST /inventory` ist ein Alias. Alle zusätzlichen Pipeline-Felder bleiben erhalten; der Service ergänzt `received_at` und `warehouse_instance`.

```json
{"batch_id":"MET-101","material":"Eisen","weight_kg":500,"shape":"Barren","quality":"PASSED"}
```

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/store -ContentType 'application/json' -Body '{"batch_id":"MET-101","material":"Eisen","weight_kg":500,"shape":"Barren","quality":"PASSED"}'
```

201: gespeichert; 409: Batch-ID existiert bereits; 422: ungültige Daten. Qualität muss `PASSED` oder `REJECTED` sein. Auch zurückgewiesene Chargen werden erfasst und im Dashboard separat ausgewiesen. Gewicht muss positiv und endlich sein. Wiederholte Zustellungen werden anhand der Batch-ID innerhalb der laufenden Instanz erkannt. GET `/inventory` liefert ein JSON-Array. GET `/health` dient als Bereitschafts- und Lebenszeichenprüfung.

## Multi-Node-Cluster

```powershell
docker build -t warehouse:1.0.0 .
# Image in eure Registry pushen und image in k8s.yaml entsprechend ersetzen.
kubectl apply -f k8s.yaml
kubectl port-forward service/warehouse 8000:80
```

Das Image muss auf allen möglichen Nodes verfügbar sein. Das Deployment nutzt genau eine Replik und einen Uvicorn-Worker, da die Python-Liste pro Prozess existiert. Der Pod kann auf einem beliebigen geeigneten Node laufen. Recreate verhindert bei Updates parallele Warehouse-Pods, verursacht aber eine kurze Unterbrechung. Neustarts, Updates oder Node-Ausfälle löschen den gesamten Bestand. Nicht horizontal skalieren, solange kein gemeinsamer Speicher eingeführt wurde. Das Manifest enthält Ressourcenlimits, Health-Probes und einen Benutzer ohne Root-Rechte.

Demo-Daten werden nur über den expliziten Demo-Button erzeugt. Compose aktiviert den Demo-Endpunkt; Kubernetes deaktiviert ihn. Keine Beispielchargen werden beim Start eingelagert. Ohne Demo zeigt der Button eine entsprechende Meldung.

Der Service enthält keine Authentifizierung und ist für das interne Fabriknetz vorgesehen. Externen Zugriff bei Bedarf über euren geschützten Ingress bereitstellen. Das Dashboard funktioniert ohne externe JavaScript-Bibliotheken; optionale Google-Schriftarten haben lokale Fallbacks. Animationen berücksichtigen die Systemeinstellung für reduzierte Bewegung.

## HTTP-Zugriff im Cluster

Der Service nimmt HTTP auf Port 80 entgegen und leitet an Container-Port 8000 weiter. Der Traefik-Ingress routet HTTP-Anfragen auf Pfad / ohne Host-Einschraenkung zum Warehouse. Nach dem Apply ist das Dashboard bei aktivem Traefik/ServiceLB unter http://<NODE-IP>/ erreichbar. Die Security Group muss Port 80 fuer den Client zulassen. Fuer weitere Frontends eigene Hostnamen oder spezifische Ingress-Regeln verwenden. Image-Neubau ist fuer diese Manifest-Aenderung nicht erforderlich.
