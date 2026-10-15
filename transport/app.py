import os
import time
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

SMELTING_URL = os.environ.get("SMELTING_URL", "http://melting-service:80/smelt")
DB_HOST = os.environ.get("DB_HOST", "postgres-cluster-rw")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "app")
DB_USER = os.environ.get("DB_USER", "app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

fallback_materials = []

def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=3
    )

def init_db():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transport (
                        id SERIAL PRIMARY KEY,
                        batch_id VARCHAR(128) NOT NULL,
                        material VARCHAR(128) NOT NULL,
                        weight_kg NUMERIC(10, 2) NOT NULL,
                        location VARCHAR(64) DEFAULT 'furnace',
                        status VARCHAR(64) DEFAULT 'forwarded',
                        note TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            conn.commit()
    except Exception:
        pass

init_db()

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "transport"}), 200

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/transport", methods=["POST"])
def handle_transport():
    data = request.get_json(force=True) or {}
    time.sleep(2)
    data["location"] = "furnace"

    batch_id = data.get("batch_id", "MET-UNKNOWN")
    material = data.get("material", "Unbekannt")
    weight_kg = float(data.get("weight_kg", 0))
    note = data.get("note", "")

    status = "forwarded"
    status_code = 200
    smelting_response = None

    try:
        res = requests.post(SMELTING_URL, json=data, timeout=10)
        status_code = res.status_code
        smelting_response = res.json() if res.headers.get("Content-Type") == "application/json" else res.text
    except requests.exceptions.RequestException as e:
        status = "transport_completed_but_smelting_unreachable"
        status_code = 502
        smelting_response = str(e)

    record = {
        "batch_id": batch_id,
        "material": material,
        "weight_kg": weight_kg,
        "location": "furnace",
        "status": status,
        "note": note,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    fallback_materials.insert(0, record)

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO transport (batch_id, material, weight_kg, location, status, note, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW());
                """, (batch_id, material, weight_kg, "furnace", status, note))
            conn.commit()
    except Exception:
        pass

    return jsonify({
        "status": status,
        "data": data,
        "smelting_response": smelting_response
    }), status_code

@app.route("/api/materials", methods=["GET"])
def get_materials():
    materials = []
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, batch_id, material, weight_kg, location, status, note, created_at FROM transport ORDER BY created_at DESC, id DESC LIMIT 100;")
                rows = cur.fetchall()
                for r in rows:
                    item = dict(r)
                    item["weight_kg"] = float(item["weight_kg"]) if item.get("weight_kg") is not None else 0.0
                    item["created_at"] = item["created_at"].strftime("%Y-%m-%d %H:%M:%S") if hasattr(item.get("created_at"), "strftime") else str(item.get("created_at", ""))
                    materials.append(item)
    except Exception:
        materials = fallback_materials[:100]

    return jsonify(materials), 200

@app.route("/api/stats", methods=["GET"])
def get_stats():
    total_count = len(fallback_materials)
    total_weight = sum(m.get("weight_kg", 0) for m in fallback_materials)
    db_connected = False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(weight_kg), 0) as total_wt FROM transport;")
                row = cur.fetchone()
                if row:
                    total_count = int(row["cnt"])
                    total_weight = float(row["total_wt"])
                db_connected = True
    except Exception:
        pass

    return jsonify({
        "total_batches": total_count,
        "total_weight_kg": total_weight,
        "total_weight_tonnes": round(total_weight / 1000.0, 3),
        "db_connected": db_connected,
        "smelting_url": SMELTING_URL
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
