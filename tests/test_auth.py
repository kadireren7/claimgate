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


@pytest.mark.asyncio
async def test_unauthenticated_app_route_redirects_to_login(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        response = await client.get("/app")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_unauthenticated_app_subroute_redirects_to_login(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        response = await client.get("/app/workflows")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_run_and_execution_apis_require_session(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anonymous_list = await client.get("/api/runs")
        anonymous_start = await client.post(
            "/api/runs",
            json={"preset": "safe", "policy_profile": "standard-contract-v1"},
        )
        anonymous_detail = await client.get("/api/runs/unknown")
        anonymous_pdf = await client.get("/api/runs/unknown/pdf")
        anonymous_approval = await client.post(
            "/api/runs/unknown/approve-and-send", json={"confirmed": True}
        )

        assert anonymous_list.status_code == 401
        assert anonymous_start.status_code == 401
        assert anonymous_detail.status_code == 401
        assert anonymous_pdf.status_code == 401
        assert anonymous_approval.status_code == 401

        signup = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        assert signup.status_code == 201
        authenticated_list = await client.get("/api/runs")
        authenticated_missing = await client.get("/api/runs/unknown")

    assert authenticated_list.status_code == 200
    assert authenticated_missing.status_code == 404


@pytest.mark.asyncio
async def test_signup_login_reach_app_and_logout_blocks_again(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        signup = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        assert signup.status_code == 201
        assert signup.json()["user"]["email"] == "ada@example.com"
        assert "claimgate_session" in client.cookies

        app_page = await client.get("/app")
        assert app_page.status_code == 200
        assert "Authorization operations at a glance" in app_page.text

        session = await client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["user"]["full_name"] == "Ada Operator"

        logout = await client.post("/api/auth/logout")
        assert logout.status_code == 200

        blocked_again = await client.get("/app")
        assert blocked_again.status_code == 302
        assert blocked_again.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_with_valid_credentials_reaches_app(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        await client.post("/api/auth/logout")

        login = await client.post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": SIGNUP_PAYLOAD["password"]},
        )
        assert login.status_code == 200

        app_page = await client.get("/app/workflows")
        assert app_page.status_code == 200


@pytest.mark.asyncio
async def test_login_with_invalid_credentials_fails_safely(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=False
    ) as client:
        await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        await client.post("/api/auth/logout")

        bad_password = await client.post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": "wrong password entirely"},
        )
        assert bad_password.status_code == 401
        assert "claimgate_session" not in client.cookies

        unknown_email = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever-it-is"},
        )
        assert unknown_email.status_code == 401

        still_blocked = await client.get("/app")
        assert still_blocked.status_code == 302


@pytest.mark.asyncio
async def test_signup_rejects_mismatched_passwords_and_duplicate_email(
    tmp_path: Path,
) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mismatched = await client.post(
            "/api/auth/signup",
            json={**SIGNUP_PAYLOAD, "confirm_password": "a different password"},
        )
        assert mismatched.status_code == 400

        first = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        assert first.status_code == 201

        duplicate = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
        assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_compat_routes_remain_unauthenticated(tmp_path: Path) -> None:
    """Existing (pre-Phase-17) routes are kept exactly as they were —
    unauthenticated — for backward compatibility, per the Phase 17 spec."""

    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/workflows",
            "/approvals",
            "/evidence",
            "/policies",
            "/audit",
            "/integrations",
            "/security",
            "/settings",
        ):
            response = await client.get(path)
            assert response.status_code == 200, path


@pytest.mark.asyncio
async def test_forgot_password_never_leaks_account_existence(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)

        known = await client.post(
            "/api/auth/forgot-password", json={"email": "ada@example.com"}
        )
        unknown = await client.post(
            "/api/auth/forgot-password", json={"email": "nobody@example.com"}
        )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
