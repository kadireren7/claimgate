"""Fixed Phase 0 document content used by both manual spikes."""

from __future__ import annotations

from pathlib import Path

DEFAULT_PDF_PATH = Path("artifacts/phase0-agreement.pdf")

FIXED_TAGGED_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>ClaimGate Phase 0 Agreement</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 56px; color: #172033; }
    h1 { color: #173f73; }
    .terms { margin: 32px 0; padding: 20px; border: 1px solid #9ba8b8; }
    .signature { margin-top: 72px; border-top: 1px solid #172033; padding-top: 8px; }
    .esign-tag { color: #ffffff; font-size: 8px; }
  </style>
</head>
<body>
  <h1>ClaimGate Phase 0 Agreement</h1>
  <p>This fixed document verifies the Foxit PDF and eSign integration path.</p>
  <div class="terms">
    <strong>Demo term:</strong> The recipient acknowledges this non-production integration test.
  </div>
  <div class="signature">
    Authorized recipient signature
    <span class="esign-tag">${s:1:______}</span>
  </div>
</body>
</html>
"""

