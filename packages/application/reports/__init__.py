"""Build report bytes only when the immutable source hash matches its record."""

import hashlib
from pathlib import Path

from packages.reports import ReportSpec, render_html


def render_verified_html(spec: ReportSpec, source_pdf: Path) -> bytes:
    if hashlib.sha256(source_pdf.read_bytes()).hexdigest() != spec.source_sha256:
        raise ValueError("source PDF hash differs from report input")
    return render_html(spec).encode("utf-8")


__all__ = ("render_verified_html",)
