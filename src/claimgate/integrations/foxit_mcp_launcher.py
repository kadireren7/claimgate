"""Compatibility launcher for the pinned official Foxit MCP server."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Expected the official Foxit MCP project directory", file=sys.stderr)
        return 64

    status_value = 70
    status_path = Path(os.environ["CLAIMGATE_FOXIT_MCP_STATUS_PATH"])
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        print("Unable to find uv for the Foxit MCP subprocess", file=sys.stderr)
        status_path.write_text(str(status_value), encoding="utf-8")
        return status_value

    command = [
        uv_executable,
        "--directory",
        str(Path(sys.argv[1]).resolve()),
        "run",
        "python",
        "-c",
        (
            "from foxit_pdf_api_mcp_server.server import mcp; "
            "mcp.run(transport='stdio', show_banner=False)"
        ),
    ]
    try:
        status_value = subprocess.run(command, check=False).returncode
    finally:
        status_path.write_text(str(status_value), encoding="utf-8")
        print(f"FOXIT_MCP_EXIT_STATUS={status_value}", file=sys.stderr)
    return status_value


if __name__ == "__main__":
    raise SystemExit(main())
