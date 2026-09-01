from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from claimgate.web.app import create_app

SIGNUP_PAYLOAD = {
    "full_name": "Ada Operator",
    "email": "ada@example.com",
    "workspace_name": "Ada's Workspace",
    "password": "correct horse battery",
    "confirm_password": "correct horse battery",
}


def build_app(tmp_path: Path):
    return create_app(artifact_directory=tmp_path / "web-artifacts")


async def _sign_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_upload_requires_session(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/uploads",
            data={"kind": "evidence"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_file_is_accepted_and_stored_under_server_generated_id(
    tmp_path: Path,
) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        response = await client.post(
            "/api/uploads",
            data={"kind": "evidence"},
            files={"file": ("../../etc/passwd.txt", b"supporting evidence text", "text/plain")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["kind"] == "evidence"
        # The path traversal attempt is stripped down to a bare, safe filename —
        # the browser-supplied path component never reaches the filesystem.
        assert payload["filename"] == "passwd.txt"
        assert "upload_id" in payload and len(payload["upload_id"]) == 24

        listing = await client.get("/api/uploads")
        assert listing.status_code == 200
        assert len(listing.json()["uploads"]) == 1

        uploads_dir = tmp_path / "web-artifacts" / "uploads"
        stored_files = list(uploads_dir.iterdir())
        assert len(stored_files) == 1
        # Stored filename is prefixed with the server-generated id, never the
        # raw client path.
        assert stored_files[0].name.startswith(payload["upload_id"])
        assert ".." not in stored_files[0].name


@pytest.mark.asyncio
async def test_unsupported_file_type_is_rejected(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        response = await client.post(
            "/api/uploads",
            data={"kind": "artifact"},
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_file_is_rejected(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    oversized_content = b"0" * (10 * 1024 * 1024 + 1)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        response = await client.post(
            "/api/uploads",
            data={"kind": "artifact"},
            files={"file": ("agreement.pdf", oversized_content, "application/pdf")},
        )
    assert response.status_code == 400
    assert "upload limit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_cannot_be_removed_by_a_different_user(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as owner:
        await _sign_up(owner)
        created = await owner.post(
            "/api/uploads",
            data={"kind": "evidence"},
            files={"file": ("notes.txt", b"owner evidence", "text/plain")},
        )
        upload_id = created.json()["upload_id"]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        await other.post(
            "/api/auth/signup",
            json={**SIGNUP_PAYLOAD, "email": "other@example.com"},
        )
        response = await other.delete(f"/api/uploads/{upload_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_owner_can_remove_own_upload(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        created = await client.post(
            "/api/uploads",
            data={"kind": "evidence"},
            files={"file": ("notes.txt", b"owner evidence", "text/plain")},
        )
        upload_id = created.json()["upload_id"]

        deleted = await client.delete(f"/api/uploads/{upload_id}")
        assert deleted.status_code == 200

        listing = await client.get("/api/uploads")
        assert listing.json()["uploads"] == []
