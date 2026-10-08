"""
Unit & Integration Test fuer den Casting & Inspection Service.
Testet:
1. Gießvorgang: Ergaenzt 'shape': 'Barren'
2. Qualitaetspruefung: 'quality' ist 'PASSED' oder 'REJECTED'
3. Datensatz-Struktur entspricht exakt den Vorgaben
4. REST API Endpunkte (/cast, /api/stats, /health, /)
"""

import json
import unittest
from app import app, stats

class TestCastingService(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        stats["simulate_delay_sec"] = 0.0 # Tests schnell ausfuehren

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")

    def test_cast_pipeline_logic(self):
        # Eingangsdaten vom Schmelzofen (Smelting Service 3)
        smelting_input = {
            "batch_id": "MET-101",
            "material": "Eisen",
            "weight_kg": 500,
            "status": "liquid",
            "temp_celsius": 1450
        }

        resp = self.client.post(
            "/cast",
            data=json.dumps(smelting_input),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        result = resp.get_json()

        self.assertEqual(result["status"], "success")
        self.assertIn(result["quality"], ["PASSED", "REJECTED"])

        out_data = result["data"]
        # Spezifikationspruefung:
        # { "batch_id": "MET-101", "material": "Eisen", "weight_kg": 500, "shape": "Barren", "quality": "PASSED" }
        self.assertEqual(out_data["batch_id"], "MET-101")
        self.assertEqual(out_data["material"], "Eisen")
        self.assertEqual(out_data["weight_kg"], 500)
        self.assertEqual(out_data["shape"], "Barren")
        self.assertIn(out_data["quality"], ["PASSED", "REJECTED"])

    def test_dashboard_ui_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Casting & Qualitätsprüfung", html)
        self.assertIn("POST /cast", html)

    def test_api_stats(self):
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("metrics", data)
        self.assertIn("config", data)

if __name__ == "__main__":
    unittest.main()
