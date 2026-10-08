import os
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

SMELTING_URL = os.environ.get("SMELTING_URL", "http://smelting-service:80/smelt")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "transport"}), 200

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "2. Transport Service",
        "next_service": SMELTING_URL,
        "usage": "POST /transport mit z. B. {'batch_id': 'MET-101', 'material': 'Eisen', 'weight_kg': 500}"
    }), 200

@app.route("/transport", methods=["POST"])
def handle_transport():
    data = request.get_json(force=True)

    time.sleep(2)

    data["location"] = "furnace"

    try:
        response = requests.post(SMELTING_URL, json=data, timeout=10)
        return jsonify({
            "status": "forwarded",
            "data": data,
            "smelting_response": response.json() if response.headers.get("Content-Type") == "application/json" else response.text
        }), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({
            "status": "transport_completed_but_smelting_unreachable",
            "data": data,
            "error": str(e)
        }), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
