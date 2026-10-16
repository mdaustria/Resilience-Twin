"""Task 3.1 configuration and local validator selection checks."""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

from scripts.probe_document_tools import fixture_bytes, inspect_pdf

ROOT = Path(__file__).resolve().parents[2]


def test_provider_config_is_exact_and_disabled_until_verified() -> None:
    content = (ROOT / "release/providers.json").read_text(encoding="utf-8")
    config = json.loads(content)
    guest = config["guest_access"]
    assert guest["mode"] == "temporary_session_only"
    assert guest["end_user_firebase_auth_required"] is False
    assert guest["account_recovery_supported"] is False
    assert guest["server_sdk"] == "firebase-admin==7.7.0"
    assert "firebase_auth" not in config
    gemini = config["gemini"]
    assert gemini["sdk"] == "google-genai==2.29.0"
    assert gemini["model_id"] == "gemini-3.8-flash"
    assert gemini["api_version"] == "v1"
    assert gemini["enabled"] is False
    assert gemini["live_probe_status"] == "synthetic_pdf_verified"
    assert gemini["model_lookup_verified_at"] == "2026-10-13T07:34:38.733687+00:00"
    assert gemini["live_probe_verified_at"] == "2026-10-13T07:36:30.994002+00:00"
    assert gemini["returned_model_version"] == "gemini-3.8-flash"
    assert gemini["live_probe_usage"] == {
        "input_tokens": 538,
        "output_tokens": 1,
        "thinking_tokens": 24,
        "total_tokens": 563,
        "max_output_tokens": 64,
        "synthetic_pdf_bytes": 431,
    }
    assert gemini["estimated_paid_standard_cost_usd"] == 0.00049725
    assert gemini["project_id"] == "ai-projects-250716"
    assert gemini["billing_model"] == "postpay"
    assert gemini["billing_tier"] == "tier_3"
    assert gemini["key_restrictions"] == "gemini_only_owner_confirmed"
    assert gemini["project_spend_cap_usd"] == 50
    assert gemini["requested_controls"] == {
        "status": "superseded_by_owner_confirmation_2026-10-14",
        "key_api_restriction": "Generative Language API",
        "project_monthly_spend_cap_usd": 5,
        "project_log_retention_days": 7,
        "data_sharing_enabled": False,
    }
    owner = gemini["owner_reported_controls"]
    assert owner["key_type"] == "authorization"
    assert owner["project_monthly_spend_cap_usd"] == 50
    assert owner["active_interactive_limits"] == {
        "rpm": {"displayed_usage": 1, "displayed_limit": 20000},
        "tpm": {"displayed_usage": 538, "displayed_limit": 20000000},
        "rpd": {"displayed_usage": 1, "displayed_limit": "unlimited"},
    }
    assert owner["project_log_retention_days"] == 7
    assert owner["data_sharing_enabled"] is False
    assert config["pdf_validation"]["linux_ci_scanner_verified"] is True
    assert config["pdf_validation"]["linux_ci_scanner_run"].endswith("/38518985622")
    assert gemini["synthetic_probe_cost_cap_usd"] == 0.01
    assert gemini["quota"]["spend_rate_limit_usd_per_10_minutes"] == 200
    assert gemini["provider_retention"]["abuse_monitoring_days"] == 55
    assert gemini["provider_retention"]["paid_content_used_for_product_improvement"] is False
    assert gemini["allow_global_fallback"] is False
    assert gemini["credential_env"] == "GEMINI_API_KEY"
    assert "key_value" not in content
    assert "---" not in content
    assert version("google-genai") == "2.29.0"
    assert version("pypdf") == "6.20.1"


def test_pdf_probe_rejects_bounded_unsafe_cases() -> None:
    cases = fixture_bytes()
    outcomes = {name: inspect_pdf(name, data) for name, data in cases.items()}
    assert outcomes["clean"].status == "accepted"
    assert outcomes["clean"].page_count == 1
    assert outcomes["encrypted"].reason == "encrypted PDF"
    assert outcomes["javascript"].reason == "active PDF content"
    assert outcomes["malformed"].status == "rejected"
    assert outcomes["oversized"].reason == "probe byte limit"
