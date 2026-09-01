from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from claimgate.integrations import foxit_mcp_launcher


def test_launcher_uses_synchronous_fastmcp_api_and_records_status(
    tmp_path: Path, monkeypatch
) -> None:
    status_path = tmp_path / "exit-status"
    official_directory = tmp_path / "official-server"
    captured_command: list[str] = []

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        assert check is False
        captured_command.extend(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("CLAIMGATE_FOXIT_MCP_STATUS_PATH", str(status_path))
    monkeypatch.setattr(sys, "argv", ["foxit-mcp-launcher", str(official_directory)])
    monkeypatch.setattr(foxit_mcp_launcher.shutil, "which", lambda _: "/tools/uv")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert foxit_mcp_launcher.main() == 0
    assert status_path.read_text() == "0"
    assert captured_command[:6] == [
        "/tools/uv",
        "--directory",
        str(official_directory),
        "run",
        "python",
        "-c",
    ]
    launch_code = captured_command[6]
    assert "from foxit_pdf_api_mcp_server.server import mcp" in launch_code
    assert "mcp.run(transport='stdio', show_banner=False)" in launch_code
    assert "asyncio.run" not in launch_code
