"""Manually send the fixed tagged PDF through Foxit eSign."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from claimgate.config import ConfigurationError, FoxitESignSettings
from claimgate.integrations.foxit_esign import FoxitESignClient, Signer
from claimgate.phase0 import DEFAULT_PDF_PATH


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is not set: {name}")
    return value


def main() -> None:
    load_dotenv()
    if os.getenv("FOXIT_ESIGN_CONFIRM_SEND") != "YES":
        raise SystemExit(
            "Refusing to send a real signing email. Set FOXIT_ESIGN_CONFIRM_SEND=YES "
            "after checking the recipient."
        )

    signer = Signer(
        email=_required("FOXIT_ESIGN_RECIPIENT_EMAIL"),
        first_name=_required("FOXIT_ESIGN_RECIPIENT_FIRST_NAME"),
        last_name=_required("FOXIT_ESIGN_RECIPIENT_LAST_NAME"),
    )
    pdf_path = Path(os.getenv("CLAIMGATE_PHASE0_PDF", str(DEFAULT_PDF_PATH))).resolve()
    print(f"Sending {pdf_path} to {signer.email} through Foxit eSign...")

    with FoxitESignClient(FoxitESignSettings.from_env()) as client:
        result = client.send_pdf_for_signature(pdf_path, signer)
    print(f"Foxit eSign folder {result.folder_id} sent to {signer.email}")


if __name__ == "__main__":
    main()

