import http.server
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from argos.runner import run_one
from argos_examples import apply_env, pack


class Handler(http.server.BaseHTTPRequestHandler):
    status_code = 200
    body = b"Preview before commit."

    def do_GET(self):
        self.send_response(type(self).status_code)
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):
        pass


class Cases(unittest.TestCase):
    def setUp(self):
        Handler.status_code = 200
        Handler.body = b"Preview before commit."
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = patch.dict("os.environ", {"ARGOS_BASE_URL": f"http://127.0.0.1:{self.server.server_port}"}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def execute(self, index=0):
        with tempfile.TemporaryDirectory() as temp:
            return run_one(pack().load_cases()[index], Path(temp), lambda _: None)

    def test_health_and_preview_pass(self):
        self.assertEqual(self.execute().status, "pass")
        self.assertEqual(self.execute(1).status, "pass")

    def test_http_error_fails(self):
        Handler.status_code = 503
        self.assertEqual(self.execute().status, "fail")

    def test_missing_text_fails(self):
        Handler.body = b"Wrong application"
        self.assertEqual(self.execute(1).status, "fail")

    def test_threshold_is_enforced(self):
        with patch.dict("os.environ", {"ARGOS_MAX_LATENCY_MS": "0.000001"}):
            self.assertEqual(self.execute().status, "fail")

    def test_remote_environment_requires_explicit_target(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                apply_env("preview")
