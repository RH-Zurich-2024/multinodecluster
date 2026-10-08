import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

try:
    from delivery.delivery import DeliveryHandler
    import delivery.delivery as delivery_module
except ModuleNotFoundError:
    from delivery import DeliveryHandler
    import delivery as delivery_module


class MockTransportResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DeliveryHandler)

    def tearDown(self):
        self.server.server_close()

    @patch.object(delivery_module, "urlopen")
    def test_deliver_adds_metadata_and_forwards_to_transport(self, mock_urlopen):
        mock_urlopen.return_value = MockTransportResponse()
        request_body = {
            "material": "Eisen",
            "weight_kg": 500,
        }

        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        thread = threading.Thread(target=self.server.handle_request)
        thread.start()
        connection.request(
            "POST",
            "/deliver",
            body=json.dumps(request_body),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response_body = json.loads(response.read())
        thread.join()
        connection.close()

        self.assertEqual(response.status, 200)
        self.assertEqual(response_body["material"], "Eisen")
        self.assertEqual(response_body["weight_kg"], 500)
        self.assertRegex(response_body["batch_id"], r"^[0-9A-F]{8}$")
        self.assertRegex(
            response_body["timestamp"],
            r"^\d{4}-\d{2}-\d{2}T.*\+00:00$",
        )

        forwarded_request = mock_urlopen.call_args.args[0]
        forwarded_body = json.loads(forwarded_request.data)
        self.assertEqual(forwarded_body, response_body)
        self.assertEqual(
            forwarded_request.get_header("Content-type"),
            "application/json",
        )


if __name__ == "__main__":
    unittest.main()
