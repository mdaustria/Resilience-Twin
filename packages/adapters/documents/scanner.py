"""Fail-closed ClamAV scan adapter for quarantined PDFs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from packages.application.documents import IntakeError


class ClamAvScanner:
    def __init__(self, executable: Path, database: Path) -> None:
        self.executable = executable
        self.database = database

    def scan(self, quarantined_path: Path) -> None:
        if not self.executable.is_file() or not self.database.is_dir():
            raise IntakeError("scanner_unavailable", "The PDF scanner is unavailable.")
        try:
            result = subprocess.run(
                [str(self.executable), "--no-summary", f"--database={self.database}", "--fail-if-cvd-older-than=2", str(quarantined_path)],
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IntakeError("scan_failed", "The PDF scan could not complete.") from exc
        if result.returncode == 1:
            raise IntakeError("unsafe_pdf", "The PDF scanner rejected this file.")
        if result.returncode != 0:
            raise IntakeError("scan_failed", "The PDF scan could not complete.")


__all__ = ["ClamAvScanner"]
