"""Extract text from a browser-downloaded report with the approved pypdf runtime."""

import sys

from pypdf import PdfReader

print("\n".join(page.extract_text() for page in PdfReader(sys.argv[1]).pages))
