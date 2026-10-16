"""One bounded, synthetic Gemini PDF probe; never prints secrets or response text."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import UTC, datetime

import httpx
from google import genai
from google.genai import errors, types
from pypdf import PdfWriter

MODEL_ID = "gemini-3.8-flash"
API_VERSION = "v1"
MAX_OUTPUT_TOKENS = 64


def _synthetic_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lookup-only",
        action="store_true",
        help="Verify credential and model access without generating content.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print(json.dumps({"status": "missing_credential"}))
        return 2

    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(api_version=API_VERSION, timeout=20_000),
    )
    pdf = _synthetic_pdf()
    stage = "model_lookup"
    try:
        model = client.models.get(model=MODEL_ID)
        if arguments.lookup_only:
            print(
                json.dumps(
                    {
                        "status": "success",
                        "stage": stage,
                        "timestamp_utc": datetime.now(UTC).isoformat(),
                        "api": "gemini_developer_api",
                        "endpoint": "generativelanguage.googleapis.com",
                        "api_version": API_VERSION,
                        "requested_model": MODEL_ID,
                        "listed_model": getattr(model, "name", None),
                    },
                    sort_keys=True,
                )
            )
            return 0
        stage = "synthetic_pdf_generation"
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_bytes(data=pdf, mime_type="application/pdf"),
                "This is a synthetic blank one-page PDF. Reply with only the word blank.",
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW
                ),
            ),
        )
    except (errors.APIError, httpx.RequestError, TimeoutError) as exc:
        # Exception messages may include request details; report only safe diagnostics.
        code = getattr(exc, "code", None)
        provider_status = getattr(exc, "status", None)
        print(
            json.dumps(
                {
                    "status": "request_failed",
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "error_code": code if isinstance(code, int) else None,
                    "provider_status": (
                        provider_status if isinstance(provider_status, str) else None
                    ),
                }
            )
        )
        return 1
    finally:
        client.close()

    usage = response.usage_metadata
    print(
        json.dumps(
            {
                "status": "success",
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "api": "gemini_developer_api",
                "endpoint": "generativelanguage.googleapis.com",
                "api_version": API_VERSION,
                "requested_model": MODEL_ID,
                "listed_model": getattr(model, "name", None),
                "returned_model_version": response.model_version,
                "response_id": response.response_id,
                "input_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "thinking_tokens": getattr(usage, "thoughts_token_count", None),
                "total_tokens": getattr(usage, "total_token_count", None),
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "has_response_text": bool(response.text),
                "synthetic_pdf_bytes": len(pdf),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
