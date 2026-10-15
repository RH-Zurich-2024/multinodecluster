"""
Casting & Quality Inspection Service (Service 4 von 5)
Pipeline-Schritt:
1. Delivery -> 2. Transport -> 3. Smelting -> 4. Casting & Prüfung (DIESER SERVICE) -> 5. Warehouse

Features:
- Nimmt geschmolzenes Metall via POST entgegen (z. B. POST /cast oder POST /inspect)
- Formt das Metall: setzt "shape": "Barren"
- Würfelt Qualitätsprüfung: 60 % "PASSED", 40 % "REJECTED" (erhöhter Ausschuss)
- Speichert alle Batches & Metriken zentral in der PostgreSQL-Datenbank (Cluster: postgres-cluster-rw)
- Ruft per HTTP POST den Lager-Service (Warehouse) auf
- Schöne Web-UI für Monitoring, Statistiken und manuelle Test-Trigger (ohne störendes Dauer-Polling)
"""

import os
import time
import random
import logging
import threading
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

# ==============================================================================
# Konfiguration & Umgebungsvariablen
# ==============================================================================

WAREHOUSE_URL = os.environ.get("WAREHOUSE_URL", "http://warehouse:81/inventory")
DEFAULT_PASS_PROBABILITY = float(os.environ.get("PASS_PROBABILITY", "0.60"))
SIMULATE_DELAY_SEC = float(os.environ.get("SIMULATE_DELAY_SEC", "0.5"))
FORWARD_REJECTED = os.environ.get("FORWARD_REJECTED", "false").lower() in ("true", "1", "yes")

# PostgreSQL Datenbank-Konfiguration (über CloudNativePG Operator)
DB_HOST = os.environ.get("DB_HOST", "postgres-cluster-rw")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "app")
DB_USER = os.environ.get("DB_USER", "app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

# In-Memory Fallback & Thread-Safety
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


# ==============================================================================
# PostgreSQL Datenbank-Integration
# ==============================================================================

def get_db_connection():
    """Stellt eine Verbindung zur zentralen PostgreSQL-Datenbank her."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=3
        )
        return conn
    except Exception as e:
        logger.debug(f"DB-Verbindung zu {DB_HOST}:{DB_PORT} nicht möglich: {e}")
        return None


def init_db():
    """Erstellt die Metrik-Tabelle 'casting_batches', falls sie noch nicht existiert."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS casting_batches (
                        id SERIAL PRIMARY KEY,
                        batch_id VARCHAR(128) NOT NULL,
                        material VARCHAR(64),
                        weight_kg NUMERIC(10, 2),
                        shape VARCHAR(64) DEFAULT 'Barren',
                        quality VARCHAR(32) NOT NULL,
                        temp_celsius NUMERIC(10, 2),
                        status_before VARCHAR(64),
                        warehouse_status VARCHAR(255),
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_casting_batches_batch_id ON casting_batches(batch_id);
                    CREATE INDEX IF NOT EXISTS idx_casting_batches_created_at ON casting_batches(created_at DESC);
                """)
                conn.commit()
            logger.info("✅ PostgreSQL-Tabelle 'casting_batches' erfolgreich verifiziert/erstellt.")
        except Exception as e:
            logger.error(f"Fehler bei Tabellen-Initialisierung: {e}")
        finally:
            conn.close()


def save_batch_to_db(record: dict) -> bool:
    """Speichert einen verarbeiteten Batch persistent in der PostgreSQL-Tabelle."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO casting_batches 
                    (batch_id, material, weight_kg, shape, quality, temp_celsius, status_before, warehouse_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    record.get("batch_id"),
                    record.get("material"),
                    record.get("weight_kg"),
                    record.get("shape", "Barren"),
                    record.get("quality"),
                    record.get("raw_input", {}).get("temp_celsius"),
                    record.get("raw_input", {}).get("status", "liquid"),
                    record.get("warehouse_status")
                ))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern in PostgreSQL: {e}")
            conn.rollback()
        finally:
            conn.close()
    return False


# Initialisiere die DB im Hintergrund beim Start
threading.Thread(target=init_db, daemon=True).start()


# ==============================================================================
# Pipeline-Kernlogik
# ==============================================================================

def perform_casting_and_inspection(input_data: dict) -> dict:
    """
    Kernlogik für Service 4:
    - Ergänzt "shape": "Barren"
    - Würfelt Qualitätsprüfung (z.B. 60% PASSED, 40% REJECTED)
    - Versendet Datenpaket an Lager-Service (Warehouse)
    - Speichert Metrik in PostgreSQL
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

    logger.info(f"📥 Empfange Batch {batch_id} ({material}, {weight_kg}kg) aus Schmelzofen...")

    # Optionale kurze Simulation des Gießvorgangs
    if delay_sec > 0:
        time.sleep(delay_sec)

    # 1. Metall formen
    shape = "Barren"

    # 2. Qualitätsprüfung würfeln (z. B. 60% PASSED, 40% REJECTED)
    roll = random.random()
    is_passed = roll < pass_prob
    quality = "PASSED" if is_passed else "REJECTED"

    logger.info(
        f"🔍 Qualitätsprüfung für {batch_id}: {quality} (Gewürfelt: {roll:.2f}, Schwellenwert: {pass_prob:.2f})"
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
        logger.info(f"🚚 Sende {batch_id} an Lager-Service ({target_warehouse})...")
        try:
            resp = requests.post(target_warehouse, json=output_data, timeout=5)
            if resp.status_code in (200, 201):
                warehouse_status = f"Erfolgreich (HTTP {resp.status_code})"
                with data_lock:
                    stats["forwarded_to_warehouse"] += 1
                logger.info(f"✅ Batch {batch_id} erfolgreich im Warehouse eingelagert!")
            else:
                warehouse_status = f"Fehler HTTP {resp.status_code}"
                with data_lock:
                    stats["warehouse_errors"] += 1
                logger.warning(f"⚠️ Warehouse antwortete mit Statuscode {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            warehouse_status = f"Nicht erreichbar ({type(e).__name__})"
            with data_lock:
                stats["warehouse_errors"] += 1
            logger.error(f"❌ Warehouse unter {target_warehouse} nicht erreichbar: {e}")
    else:
        warehouse_status = "Ausgemustert (Ausschuss nicht eingelagert)"
        logger.info(f"🗑️ Batch {batch_id} wegen Qualitätsmangel (REJECTED) ausgemustert.")

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

    # 5. Persistent in PostgreSQL speichern
    db_saved = save_batch_to_db(record)
    if db_saved:
        logger.info(f"💾 Batch {batch_id} in PostgreSQL gespeichert.")

    # In-Memory Backup aktualisieren
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
    """
    Gibt Kennzahlen zurück. Liest primär aus der PostgreSQL-Datenbank,
    mit transparentem In-Memory Fallback.
    """
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COALESCE(COUNT(*) FILTER (WHERE quality = 'PASSED'), 0) as passed,
                        COALESCE(COUNT(*) FILTER (WHERE quality = 'REJECTED'), 0) as rejected,
                        COALESCE(COUNT(*) FILTER (WHERE warehouse_status LIKE 'Erfolgreich%'), 0) as forwarded,
                        COALESCE(COUNT(*) FILTER (WHERE warehouse_status NOT LIKE 'Erfolgreich%' AND warehouse_status NOT LIKE 'Skipped%' AND warehouse_status NOT LIKE 'Ausgemustert%'), 0) as errors
                    FROM casting_batches;
                """)
                row = cur.fetchone()
                total, passed, rejected, forwarded, errors = row
                effective_pass_rate = round((passed / total * 100), 1) if total > 0 else 0.0

                return jsonify({
                    "metrics": {
                        "total": total,
                        "passed": passed,
                        "rejected": rejected,
                        "pass_rate_percent": effective_pass_rate,
                        "forwarded_to_warehouse": forwarded,
                        "warehouse_errors": errors
                    },
                    "config": {
                        "pass_probability": stats["pass_probability"],
                        "warehouse_url": stats["warehouse_url"],
                        "simulate_delay_sec": stats["simulate_delay_sec"],
                        "forward_rejected": stats["forward_rejected"],
                        "service_started_at": stats["service_started_at"],
                        "db_connected": True,
                        "db_host": DB_HOST
                    }
                })
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der DB-Statistiken: {e}")
        finally:
            conn.close()

    # Fallback: In-Memory Stats
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
                "service_started_at": stats["service_started_at"],
                "db_connected": False,
                "db_host": DB_HOST
            }
        })


@app.route("/api/batches", methods=["GET"])
def get_batches():
    """Gibt die letzten verarbeiteten Batches zurück (aus Postgres oder Speicher)."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, batch_id, material, weight_kg, shape, quality, temp_celsius, status_before, warehouse_status, created_at
                    FROM casting_batches
                    ORDER BY created_at DESC
                    LIMIT 50;
                """)
                rows = cur.fetchall()
                db_batches = []
                for r in rows:
                    db_batches.append({
                        "id": r[0],
                        "batch_id": r[1],
                        "material": r[2],
                        "weight_kg": float(r[3]) if r[3] is not None else 0,
                        "shape": r[4] or "Barren",
                        "quality": r[5],
                        "raw_input": {"temp_celsius": float(r[6]) if r[6] is not None else None, "status": r[7]},
                        "raw_output": {"batch_id": r[1], "material": r[2], "weight_kg": float(r[3]) if r[3] is not None else 0, "shape": r[4] or "Barren", "quality": r[5]},
                        "warehouse_status": r[8],
                        "timestamp": r[9].strftime("%Y-%m-%d %H:%M:%S") if r[9] else ""
                    })
                return jsonify(db_batches)
        except Exception as e:
            logger.error(f"Fehler beim Lesen der Batches aus DB: {e}")
        finally:
            conn.close()

    # Fallback: In-Memory
    with data_lock:
        return jsonify(recent_batches)


@app.route("/api/test-batch", methods=["POST"])
def trigger_test_batch():
    """Erlaubt das manuelle Absenden eines Test-Batches direkt über die UI."""
    data = request.get_json(silent=True) or {}
    if not data:
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
            
    logger.info(f"⚙️ Konfiguration aktualisiert: Pass-Rate={stats['pass_probability']*100}%, Warehouse={stats['warehouse_url']}")
    return jsonify({"status": "updated", "config": stats})


@app.route("/api/reset-stats", methods=["POST"])
def reset_stats():
    """Setzt Zähler und Historie zurück (auch in PostgreSQL)."""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE casting_batches RESTART IDENTITY;")
                conn.commit()
            logger.info("🗑️ PostgreSQL-Tabelle 'casting_batches' wurde geleert.")
        except Exception as e:
            logger.error(f"Fehler beim Leeren der DB-Tabelle: {e}")
        finally:
            conn.close()

    with data_lock:
        stats["total_received"] = 0
        stats["passed_count"] = 0
        stats["rejected_count"] = 0
        stats["forwarded_to_warehouse"] = 0
        stats["warehouse_errors"] = 0
        recent_batches.clear()

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
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"🚀 Casting & Quality Inspection Service startet auf {host}:{port}...")
    app.run(host=host, port=port, debug=False)
