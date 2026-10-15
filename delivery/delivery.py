import json
import os
import uuid
from io import BytesIO
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TRANSPORT_SERVICE_URL = "http://transport-service:80/transport"
INDEX_FILE = Path(__file__).with_name("index.html")
DB_HOST = os.getenv("DB_HOST", "postgres-cluster-rw")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "app")
DB_USER = os.getenv("DB_USER", "app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")


class DatabaseUnavailableError(RuntimeError):
    pass


def _get_connection():
    try:
        import psycopg2
    except ImportError as error:
        raise DatabaseUnavailableError("psycopg2 is not installed") from error

    try:
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5,
        )
    except psycopg2.Error as error:
        raise DatabaseUnavailableError(str(error)) from error


def save_delivery(data):
    connection = _get_connection()
    import psycopg2

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS delivery (
                        id BIGSERIAL PRIMARY KEY,
                        batch_id VARCHAR(8) NOT NULL UNIQUE,
                        material VARCHAR(128) NOT NULL,
                        weight_kg NUMERIC NOT NULL,
                        note TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO delivery
                        (batch_id, material, weight_kg, note, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        data["batch_id"],
                        data.get("material", ""),
                        data.get("weight_kg"),
                        data.get("note"),
                        data["timestamp"],
                    ),
                )
    except psycopg2.Error as error:
        raise DatabaseUnavailableError(str(error)) from error
    finally:
        connection.close()


def get_delivery_history():
    connection = _get_connection()
    import psycopg2

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS delivery (
                        id BIGSERIAL PRIMARY KEY,
                        batch_id VARCHAR(8) NOT NULL UNIQUE,
                        material VARCHAR(128) NOT NULL,
                        weight_kg NUMERIC NOT NULL,
                        note TEXT,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    SELECT batch_id, material, weight_kg, note, created_at
                    FROM delivery
                    ORDER BY created_at DESC, id DESC
                    """
                )
                return [
                    {
                        "batch_id": row[0],
                        "material": row[1],
                        "weight_kg": float(row[2]),
                        "note": row[3],
                        "timestamp": row[4].isoformat(),
                    }
                    for row in cursor.fetchall()
                ]
    except psycopg2.Error as error:
        raise DatabaseUnavailableError(str(error)) from error
    finally:
        connection.close()

class DeliveryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            try:
                payload = INDEX_FILE.read_bytes()
            except OSError:
                self._send_json({"error": "Delivery interface unavailable"}, 500)
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if self.path == "/history":
            try:
                history = get_delivery_history()
            except DatabaseUnavailableError as error:
                self._send_json({"error": f"Database unavailable: {error}"}, 503)
                return
            self._send_json(history, 200)
            return

        self._send_json({"error": "Not found"}, 404)

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
            save_delivery(data)
        except DatabaseUnavailableError as error:
            self._send_json({"error": f"Database unavailable: {error}"}, 503)
            return

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
                    response_body = response.read()
                    raise HTTPError(
                        TRANSPORT_SERVICE_URL,
                        response.status,
                        "Transport service returned an error",
                        response.headers,
                        BytesIO(response_body),
                    )
        except (HTTPError, URLError) as error:
            error_message = str(error)
            if isinstance(error, HTTPError):
                response_body = error.read().decode("utf-8", errors="replace").strip()
                if response_body:
                    error_message = f"{error_message}: {response_body}"
            self._send_json({"error": f"Transport service unavailable: {error_message}"}, 502)
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
