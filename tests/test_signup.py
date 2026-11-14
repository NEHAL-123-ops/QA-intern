"""pytest wrapper: `python -m pytest -v` runs the full signup flow headless."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path
from threading import Thread

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import signup_automation  # noqa: E402
from signup_automation import load_data, run  # noqa: E402


def test_load_data_uses_legitimate_otp_from_config(monkeypatch):
    monkeypatch.setenv("TEST_OTP", "654321")
    data = load_data()
    assert data["otp"] == "654321"

    monkeypatch.setenv("TEST_OTP", "   ")
    with pytest.raises(ValueError, match="No verification code configured"):
        load_data()


def test_agency_signup_completes_end_to_end(monkeypatch, tmp_path):
    mock_html = (Path(__file__).resolve().parent.parent / "mock_site" / "index.html").read_bytes()

    class MockHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(mock_html)

        def log_message(self, _format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(signup_automation, "BASE_URL", base_url)
    monkeypatch.setattr(signup_automation, "REGISTER_URL", f"{base_url}/register")
    monkeypatch.setattr(signup_automation, "REPORT_DIR", tmp_path / "reports")
    monkeypatch.setenv("TEST_OTP", "123456")

    try:
        result = run(headless=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert result["status"] == "PASSED", result["failure_reason"]
    assert len(result["steps"]) == 4, "expected the mock wizard's four interactive pages"
