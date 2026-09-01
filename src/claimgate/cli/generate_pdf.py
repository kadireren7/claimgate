"""Generate the fixed Phase 0 PDF through the official Foxit MCP server."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from claimgate.config import FoxitPdfSettings
from claimgate.integrations.foxit_pdf import FoxitPdfClient
from claimgate.phase0 import DEFAULT_PDF_PATH, FIXED_TAGGED_HTML


async def _run() -> Path:
    load_dotenv()
    output = Path(os.getenv("CLAIMGATE_PHASE0_PDF", str(DEFAULT_PDF_PATH)))
    client = FoxitPdfClient(FoxitPdfSettings.from_env())
    return await client.generate_pdf_from_html(FIXED_TAGGED_HTML, output)


def main() -> None:
    output = asyncio.run(_run())
    print(f"Foxit PDF generated: {output}")


if __name__ == "__main__":
    main()

