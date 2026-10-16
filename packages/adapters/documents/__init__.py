"""Local PDF scanner and validator adapters."""

from .pdf import PypdfValidator
from .scanner import ClamAvScanner

__all__ = ["ClamAvScanner", "PypdfValidator"]
