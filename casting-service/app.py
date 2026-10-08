"""
Casting & Quality Inspection Service (Service 4 von 5)
Pipeline-Schritt:
1. Delivery -> 2. Transport -> 3. Smelting -> 4. Casting & Prüfung (DIESER SERVICE) -> 5. Warehouse

Aufgabe:
- Nimmt geschmolzenes Metall via POST entgegen (z. B. POST /cast oder POST /inspect)
- Formt das Metall: setzt "shape": "Barren"
- Würfelt Qualitätsprüfung: 90 % "PASSED", 10 % "REJECTED"
- Ruft per HTTP POST den Lager-Service (Warehouse) auf
- Schöne Web-UI für Monitoring, Live-Logs, Statistiken und manuelle Test-Trigger
"""

import os
import time
import random
import logging
from datetime import datetime
from threading import Lock
from flask import Flask, request, jsonify, render_template

# Logging Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("casting-service")

app = Flask(__name__)

# Konfiguration via Umgebungsvariablen (mit flexiblen Defaults)
WAREHOUSE_URL = os.environ.get("WAREHOUSE_URL", "http://warehouse-service:5000/inventory")
DEFAULT_PASS_PROBABILITY = float(os.environ.get("PASS_PROBABILITY", "0.90"))
SIMULATE_DELAY_SEC = float(os.environ.get("SIMULATE_DELAY_SEC", "1.0"))
FORWARD_REJECTED = os.environ.get("FORWARD_REJECTED", "false").lower() in ("true", "1", "yes")

# In-Memory Datenspeicher & Thread-Safety
data_lock = Lock()
stats = {
    "total_received": 0,
    "passed_count": 0,
    "rejected_count": 0,
    "forwarded_to_warehouse": 0,
    "warehouse_errors": 0,
    "pass_probability": DEFAULT_PASS_PROBABILITY,
    "warehouse_url": WAREHOUSE_URL,
    "simulate_delay_sec": SIMULATE_DELAY_SEC,
    "forward_rejected": FORWARD_REJECTED,
    "service_started_at": datetime.now().isoformat(),
}

recent_batches = []
MAX_HISTORY = 50

activity_logs = []
MAX_LOGS = 100

def add_log(level: str, message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"timestamp": timestamp, "level": level, "message": message}
    with data_lock:
        activity_logs.insert(0, entry)
        if len(activity_logs) > MAX_LOGS:
            activity_logs.pop()
    logger.info(message)


def perform_casting_and_inspection(input_data: dict) -> dict:
    """
    Kernlogik für Service 4:
    - Ergänzt "shape": "Barren"
    - Würfelt Qualitätsprüfung (z.B. 90% PASSED, 10% REJECTED)
    - Versendet Datenpaket an Lager-Service (Warehouse)
    """
    import requests

    batch_id = input_data.get("batch_id", f"MET-{random.randint(100, 999)}")
    material = input_data.get("material", "Eisen")
    weight_kg = input_data.get("weight_kg", 500)
    
    with data_lock:
        pass_prob = stats["pass_probability"]
        delay_sec = stats["simulate_delay_sec"]
        target_warehouse = stats["warehouse_url"]
        forward_rejected = stats["forward_rejected"]

    add_log("INFO", f"📥 Empfange Batch {batch_id} ({material}, {weight_kg}kg) aus Schmelzofen...")

    # Optionale kurze Simulation des Gießvorgangs (Abkühlen/Formen)
    if delay_sec > 0:
        time.sleep(delay_sec)

    # 1. Metall formen
    shape = "Barren"

    # 2. Qualitätsprüfung würfeln
    roll = random.random()
    is_passed = roll < pass_prob
    quality = "PASSED" if is_passed else "REJECTED"

    add_log(
        "INFO" if is_passed else "WARN",
        f"🔍 Qualitätsprüfung für {batch_id}: {quality} (Gewürfelter Wert: {roll:.2f}, Schwellenwert: {pass_prob:.2f})"
    )

    # 3. Ausgehender Datensatz gemäß Pipeline-Spezifikation:
    # { "batch_id": "MET-101", "material": "Eisen", "weight_kg": 500, "shape": "Barren", "quality": "PASSED" }
    output_data = {
        "batch_id": batch_id,
        "material": material,
        "weight_kg": weight_kg,
        "shape": shape,
        "quality": quality
    }

    # Übernehme evtl. vorherige Metadaten ohne Überschreiben
    for key, val in input_data.items():
        if key not in output_data:
            output_data[key] = val

    # 4. Weiterleitung an Warehouse Service
    warehouse_status = "Skipped"
    should_forward = is_passed or forward_rejected

    if should_forward:
        add_log("INFO", f"🚚 Sende {batch_id} an Lager-Service ({target_warehouse})...")
        try:
            resp = requests.post(target_warehouse, json=output_data, timeout=5)
            if resp.status_code in (200, 201):
                warehouse_status = f"Erfolgreich (HTTP {resp.status_code})"
                with data_lock:
                    stats["forwarded_to_warehouse"] += 1
                add_log("SUCCESS", f"✅ Batch {batch_id} erfolgreich im Warehouse eingelagert!")
            else:
                warehouse_status = f"Fehler HTTP {resp.status_code}"
                with data_lock:
                    stats["warehouse_errors"] += 1
                add_log("WARN", f"⚠️ Warehouse antwortete mit Statuscode {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            warehouse_status = f"Nicht erreichbar ({type(e).__name__})"
            with data_lock:
                stats["warehouse_errors"] += 1
            add_log("ERROR", f"❌ Warehouse unter {target_warehouse} nicht erreichbar: {e}")
    else:
        warehouse_status = "Ausgemustert (Ausschuss nicht eingelagert)"
        add_log("WARN", f"🗑️ Batch {batch_id} wegen Qualitätsmangel (REJECTED) ausgemustert.")

    # Statistiken aktualisieren
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "batch_id": batch_id,
        "material": material,
        "weight_kg": weight_kg,
        "shape": shape,
        "quality": quality,
        "raw_input": input_data,
        "raw_output": output_data,
        "warehouse_status": warehouse_status
    }

    with data_lock:
        stats["total_received"] += 1
        if is_passed:
            stats["passed_count"] += 1
        else:
            stats["rejected_count"] += 1
        
        recent_batches.insert(0, record)
        if len(recent_batches) > MAX_HISTORY:
            recent_batches.pop()

    return {
        "status": "success",
        "quality": quality,
        "warehouse_status": warehouse_status,
        "data": output_data
    }


# ==============================================================================
# Pipeline REST Endpoints (Aufruf durch Schmelz-Service 3)
# ==============================================================================

@app.route("/cast", methods=["POST"])
@app.route("/inspect", methods=["POST"])
@app.route("/process", methods=["POST"])
@app.route("/pipeline", methods=["POST"])
def pipeline_cast_endpoint():
    """
    Haupt-Endpunkt für den Schmelz-Service (Smelting).
    Erwartet JSON-Payload, z. B.:
    { "batch_id": "MET-101", "material": "Eisen", "weight_kg": 500, "status": "liquid", "temp_celsius": 1450 }
    """
    payload = request.get_json(silent=True) or {}
    result = perform_casting_and_inspection(payload)
    return jsonify(result), 200


# ==============================================================================
# UI & Dashboard Endpoints
# ==============================================================================

@app.route("/", methods=["GET"])
def dashboard():
    """Rendert die Benutzeroberfläche."""
    return render_template("index.html")


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Gibt aktuelle Kennzahlen und Konfiguration zurück."""
    with data_lock:
        total = stats["total_received"]
        passed = stats["passed_count"]
        rejected = stats["rejected_count"]
        effective_pass_rate = round((passed / total * 100), 1) if total > 0 else 0.0

        return jsonify({
            "metrics": {
                "total": total,
                "passed": passed,
                "rejected": rejected,
                "pass_rate_percent": effective_pass_rate,
                "forwarded_to_warehouse": stats["forwarded_to_warehouse"],
                "warehouse_errors": stats["warehouse_errors"]
            },
            "config": {
                "pass_probability": stats["pass_probability"],
                "warehouse_url": stats["warehouse_url"],
                "simulate_delay_sec": stats["simulate_delay_sec"],
                "forward_rejected": stats["forward_rejected"],
                "service_started_at": stats["service_started_at"]
            }
        })


@app.route("/api/batches", methods=["GET"])
def get_batches():
    """Gibt die letzten verarbeiteten Batches zurück."""
    with data_lock:
        return jsonify(recent_batches)


@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Gibt die letzten Log-Ereignisse zurück."""
    with data_lock:
        return jsonify(activity_logs)


@app.route("/api/test-batch", methods=["POST"])
def trigger_test_batch():
    """Erlaubt das manuelle Absenden eines Test-Batches direkt über die UI."""
    data = request.get_json(silent=True) or {}
    if not data:
        # Standard-Musterdaten generieren
        batch_num = random.randint(100, 999)
        materials = ["Eisen", "Stahl", "Kupfer", "Aluminium"]
        data = {
            "batch_id": f"MET-{batch_num}",
            "material": random.choice(materials),
            "weight_kg": random.choice([250, 500, 750, 1000]),
            "status": "liquid",
            "temp_celsius": random.randint(1420, 1550)
        }
    
    result = perform_casting_and_inspection(data)
    return jsonify(result), 200


@app.route("/api/config", methods=["POST"])
def update_config():
    """Aktualisiert Einstellungen zur Laufzeit."""
    data = request.get_json(silent=True) or {}
    with data_lock:
        if "pass_probability" in data:
            stats["pass_probability"] = max(0.0, min(1.0, float(data["pass_probability"])))
        if "warehouse_url" in data and data["warehouse_url"]:
            stats["warehouse_url"] = str(data["warehouse_url"]).strip()
        if "simulate_delay_sec" in data:
            stats["simulate_delay_sec"] = max(0.0, float(data["simulate_delay_sec"]))
        if "forward_rejected" in data:
            stats["forward_rejected"] = bool(data["forward_rejected"])
            
    add_log("INFO", f"⚙️ Konfiguration aktualisiert: Pass-Rate={stats['pass_probability']*100}%, Warehouse={stats['warehouse_url']}")
    return jsonify({"status": "updated", "config": stats})


@app.route("/api/reset-stats", methods=["POST"])
def reset_stats():
    """Setzt Zähler und Historie zurück."""
    with data_lock:
        stats["total_received"] = 0
        stats["passed_count"] = 0
        stats["rejected_count"] = 0
        stats["forwarded_to_warehouse"] = 0
        stats["warehouse_errors"] = 0
        recent_batches.clear()
        activity_logs.clear()
    add_log("INFO", "🔄 Zähler und Historie wurden zurückgesetzt.")
    return jsonify({"status": "reset"})


@app.route("/health", methods=["GET"])
def health():
    """Kubernetes Liveness / Readiness Probe."""
    return jsonify({
        "status": "healthy",
        "service": "casting-inspection-service",
        "step": 4,
        "name": "Casting & Quality Inspection"
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")
    add_log("INFO", f"🚀 Casting & Quality Inspection Service startet auf {host}:{port}...")
    app.run(host=host, port=port, debug=False)
