"""Environment-only configuration for Foxit integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Raised when required environment configuration is absent or invalid."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is not set: {name}")
    return value


@dataclass(frozen=True)
class FoxitPdfSettings:
    api_host: str
    client_id: str
    client_secret: str
    mcp_directory: Path

    @classmethod
    def from_env(cls) -> FoxitPdfSettings:
        directory = Path(_required("FOXIT_PDF_MCP_DIRECTORY")).expanduser().resolve()
        expected_module = directory / "src" / "foxit_pdf_api_mcp_server" / "main.py"
        if not expected_module.is_file():
            raise ConfigurationError(
                "FOXIT_PDF_MCP_DIRECTORY does not point to the official Python MCP project; "
                f"expected {expected_module}"
            )
        return cls(
            api_host=_required("FOXIT_CLOUD_API_HOST").rstrip("/"),
            client_id=_required("FOXIT_CLOUD_API_CLIENT_ID"),
            client_secret=_required("FOXIT_CLOUD_API_CLIENT_SECRET"),
            mcp_directory=directory,
        )


@dataclass(frozen=True)
class FoxitESignSettings:
    base_url: str
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> FoxitESignSettings:
        return cls(
            base_url=_required("FOXIT_ESIGN_BASE_URL").rstrip("/"),
            client_id=_required("FOXIT_ESIGN_CLIENT_ID"),
            client_secret=_required("FOXIT_ESIGN_CLIENT_SECRET"),
        )

