import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TRANSPORT_SERVICE_URL = "http://transport-service:80/transport"

class DeliveryHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deliver":
            self._send_json({"error": "Not found"}, 404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(content_length))
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "Request body must contain valid JSON"}, 400)
            return

        if not isinstance(data, dict):
            self._send_json({"error": "Request body must be a JSON object"}, 400)
            return

        data["batch_id"] = f"{uuid.uuid4().hex[:8].upper()}"
        data["timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            payload = json.dumps(data).encode("utf-8")
            request = Request(
                TRANSPORT_SERVICE_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                if response.status < 200 or response.status >= 300:
                    raise HTTPError(
                        TRANSPORT_SERVICE_URL,
                        response.status,
                        "Transport service returned an error",
                        response.headers,
                        None,
                    )
        except (HTTPError, URLError) as error:
            self._send_json({"error": f"Transport service unavailable: {error}"}, 502)
            return

        self._send_json(data, 200)

    def _send_json(self, data, status):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 80), DeliveryHandler)
    server.serve_forever()
