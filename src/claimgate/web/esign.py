"""Backend-only construction of Foxit eSign transport and recipient settings."""

from __future__ import annotations

import os
from pathlib import Path

from claimgate.config import ConfigurationError, FoxitESignSettings
from claimgate.integrations.foxit_esign import (
    ESignSendResult,
    FoxitESignClient,
    Signer,
)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is not set: {name}")
    return value


def signer_from_env() -> Signer:
    return Signer(
        email=_required("FOXIT_ESIGN_RECIPIENT_EMAIL"),
        first_name=_required("FOXIT_ESIGN_RECIPIENT_FIRST_NAME"),
        last_name=_required("FOXIT_ESIGN_RECIPIENT_LAST_NAME"),
    )


class LiveFoxitESignSender:
    """Open the credentialed transport only inside the human-approved backend call."""

    def send_pdf_for_signature(
        self, pdf_path: Path, signer: Signer
    ) -> ESignSendResult:
        if os.getenv("FOXIT_ESIGN_CONFIRM_SEND") != "YES":
            raise ConfigurationError(
                "FOXIT_ESIGN_CONFIRM_SEND=YES is required for a real eSign send"
            )
        with FoxitESignClient(FoxitESignSettings.from_env()) as client:
            return client.send_pdf_for_signature(pdf_path, signer)
