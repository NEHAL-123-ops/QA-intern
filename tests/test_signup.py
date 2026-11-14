"""pytest wrapper: `python -m pytest -v` runs the full signup flow headless."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from signup_automation import load_data, run  # noqa: E402


def test_load_data_uses_legitimate_otp_from_config(monkeypatch):
    monkeypatch.setenv("TEST_OTP", "654321")
    data = load_data()
    assert data["otp"] == "654321"

    monkeypatch.setenv("TEST_OTP", "   ")
    data = load_data()
    assert data["otp"] == "123456"


def test_agency_signup_completes_end_to_end():
    result = run(headless=True)
    assert result["status"] == "PASSED", result["failure_reason"]
    assert len(result["steps"]) >= 2, "expected a multi-page flow"
