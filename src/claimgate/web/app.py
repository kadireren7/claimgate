"""FastAPI application for the ClaimGate authorization platform."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from claimgate.actions import (
    CAPABILITY_REGISTRY,
    ActionApprovalRecord,
    action_sha256,
    authorize_action,
    is_approval_valid,
)
from claimgate.application import (
    ApprovalBoundaryError,
    ApprovalSendService,
    Phase3Progress,
    Phase3Result,
    ProfileApprovalRecord,
    build_action_approval_record,
    build_sign_document_action,
)
from claimgate.audit import (
    DecisionReceipt,
    DecisionReceiptPdfGenerator,
    ReceiptESignStatus,
    ReceiptESignSummary,
    ReceiptVerificationContext,
    canonical_receipt_json,
    issue_decision_receipt,
    verify_receipt,
)
from claimgate.domain import (
    ClaimCategory,
    PolicyOutcome,
    VerificationStatus,
    WorkflowState,
)
from claimgate.integrations.foxit_esign import Signer
from claimgate.policy_profiles import BuiltInPolicyProfile
from claimgate.public_evidence import (
    PUBLIC_EVIDENCE_SNIPPET_MARKER,
    PublicEvidenceDiscoveryResult,
    PublicEvidenceProvider,
    PublicEvidenceService,
    PublicFactType,
    ScriptedPublicEvidenceProvider,
    SerpApiPublicEvidenceProvider,
)
from claimgate.redteam import AttackRunner, AttackScenarioId
from claimgate.replay import (
    ReplayPreset,
    ReplayRequest,
    ReplayVerifier,
    apply_replay_preset,
    build_audit_timeline,
    capture_artifact_snapshot,
)
from claimgate.semantic import (
    EvidenceDocument,
    EvidenceIngestor,
    OpenAIResponsesProvider,
    ScriptedSemanticProvider,
    SemanticEngine,
    StructuredRequest,
)
from claimgate.web.auth import (
    SESSION_COOKIE_NAME,
    EmailAlreadyRegisteredError,
    SessionStore,
    UserStore,
    is_valid_email,
)
from claimgate.web.esign import LiveFoxitESignSender, signer_from_env
from claimgate.web.service import (
    PROGRESS_LABELS,
    DemoPreset,
    Phase3DemoService,
    RealDocumentReviewUnavailableError,
    preset_definition,
)
from claimgate.web.uploads import UploadRejectedError, UploadStore

LOGGER = logging.getLogger(__name__)
WEB_DIRECTORY = Path(__file__).parent
DEFAULT_ARTIFACT_DIRECTORY = Path("artifacts/web")


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    workspace_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=6, max_length=200)
    confirm_password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    email: str = Field(min_length=3, max_length=320)


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    preset: DemoPreset = Field(strict=False)
    policy_profile: BuiltInPolicyProfile = Field(
        default=BuiltInPolicyProfile.STANDARD_CONTRACT,
        strict=False,
    )


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    upload_id: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=20_000)
    title: str = Field(default="Supporting evidence", min_length=1, max_length=200)


class StartDocumentRunRequest(BaseModel):
    """Start a workflow from a real uploaded document, not a fixed preset."""

    model_config = ConfigDict(extra="forbid", strict=True)

    artifact_upload_id: str = Field(min_length=1, max_length=64)
    evidence: list[EvidenceInput] = Field(min_length=1, max_length=10)
    policy_profile: BuiltInPolicyProfile = Field(
        default=BuiltInPolicyProfile.STANDARD_CONTRACT,
        strict=False,
    )


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    confirmed: bool


class ReplayApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preset: ReplayPreset = Field(default=ReplayPreset.CLEAN_REPLAY, strict=False)


class StartupConfigurationError(RuntimeError):
    """Raised at app startup when an explicitly selected live provider is missing
    its required credentials. Only checked when a live mode is explicitly
    requested; the default scripted/simulated configuration never raises this."""


def _validate_startup_configuration() -> None:
    problems: list[str] = []
    semantic_provider = os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").strip().lower()
    if semantic_provider == "openai" and not os.getenv("OPENAI_API_KEY", "").strip():
        problems.append(
            "CLAIMGATE_SEMANTIC_PROVIDER=openai requires OPENAI_API_KEY to be set."
        )
    public_evidence_provider = (
        os.getenv("CLAIMGATE_PUBLIC_EVIDENCE_PROVIDER", "scripted").strip().lower()
    )
    if public_evidence_provider == "serpapi" and not os.getenv("SERPAPI_API_KEY", "").strip():
        problems.append(
            "CLAIMGATE_PUBLIC_EVIDENCE_PROVIDER=serpapi requires SERPAPI_API_KEY to be set."
        )
    if os.getenv("FOXIT_ESIGN_CONFIRM_SEND", "").strip() == "YES":
        required_for_live_send = (
            "FOXIT_ESIGN_BASE_URL",
            "FOXIT_ESIGN_CLIENT_ID",
            "FOXIT_ESIGN_CLIENT_SECRET",
            "FOXIT_ESIGN_RECIPIENT_EMAIL",
            "FOXIT_ESIGN_RECIPIENT_FIRST_NAME",
            "FOXIT_ESIGN_RECIPIENT_LAST_NAME",
        )
        missing = [name for name in required_for_live_send if not os.getenv(name, "").strip()]
        if missing:
            problems.append(
                "FOXIT_ESIGN_CONFIRM_SEND=YES but missing: " + ", ".join(missing)
            )
    if problems:
        raise StartupConfigurationError(
            "ClaimGate startup configuration is invalid:\n- " + "\n- ".join(problems)
        )


def _diagnostics_snapshot() -> dict[str, object]:
    """Safe, secret-free configuration metadata for judges/operators."""

    foxit_pdf_configured = all(
        os.getenv(name, "").strip()
        for name in (
            "FOXIT_CLOUD_API_HOST",
            "FOXIT_CLOUD_API_CLIENT_ID",
            "FOXIT_CLOUD_API_CLIENT_SECRET",
            "FOXIT_PDF_MCP_DIRECTORY",
        )
    )
    foxit_esign_configured = all(
        os.getenv(name, "").strip()
        for name in ("FOXIT_ESIGN_BASE_URL", "FOXIT_ESIGN_CLIENT_ID", "FOXIT_ESIGN_CLIENT_SECRET")
    )
    return {
        "foxit_pdf_configured": foxit_pdf_configured,
        "foxit_esign_configured": foxit_esign_configured,
        "serpapi_configured": bool(os.getenv("SERPAPI_API_KEY", "").strip()),
        "semantic_provider": os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").strip().lower()
        or "scripted",
        "public_evidence_provider": os.getenv(
            "CLAIMGATE_PUBLIC_EVIDENCE_PROVIDER", "scripted"
        ).strip().lower()
        or "scripted",
        "live_sending_enabled": os.getenv("FOXIT_ESIGN_CONFIRM_SEND", "").strip() == "YES",
    }


@dataclass
class DemoRun:
    run_id: str
    output_path: Path
    preset: DemoPreset | None = None
    policy_profile: BuiltInPolicyProfile = BuiltInPolicyProfile.STANDARD_CONTRACT
    is_document_run: bool = False
    owner_user_id: str | None = None
    source_filename: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: RunStatus = RunStatus.RUNNING
    progress_history: list[Phase3Progress] = field(default_factory=list)
    result: Phase3Result | None = None
    public_error: str | None = None
    send_attempted: bool = False
    send_state: WorkflowState | None = None
    esign_folder_id: str | None = None
    send_error: str | None = None
    profile_approval: ProfileApprovalRecord | None = None
    action_approval: ActionApprovalRecord | None = None
    receipt_history: list[ReceiptChainEntry] = field(default_factory=list)
    receipt_pdf_path: Path | None = None
    receipt_pdf_hash: str | None = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    receipt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    public_evidence_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    public_evidence_attempted: set[str] = field(default_factory=set)
    public_discoveries: dict[str, PublicEvidenceDiscoveryResult] = field(
        default_factory=dict
    )
    stage_started_at: dict[str, float] = field(default_factory=dict)
    stage_duration_ms: dict[str, float] = field(default_factory=dict)

    def observe(self, progress: Phase3Progress) -> None:
        now = time.monotonic()
        if self.progress_history and self.progress_history[-1] is progress:
            return
        if self.progress_history:
            previous = self.progress_history[-1].value
            started = self.stage_started_at.get(previous)
            if started is not None:
                self.stage_duration_ms[previous] = round((now - started) * 1000, 1)
        self.progress_history.append(progress)
        self.stage_started_at[progress.value] = now

    def finish_timing(self) -> None:
        if not self.progress_history:
            return
        last = self.progress_history[-1].value
        started = self.stage_started_at.get(last)
        if started is not None and last not in self.stage_duration_ms:
            self.stage_duration_ms[last] = round((time.monotonic() - started) * 1000, 1)


@dataclass(frozen=True)
class ReceiptChainEntry:
    sequence: int
    expected_previous_receipt_sha256: str | None
    receipt: DecisionReceipt
    approval: ProfileApprovalRecord | None
    esign: ReceiptESignSummary


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, DemoRun] = {}
        self._last_receipt_sha256: str | None = None
        self._receipt_count = 0

    def add(self, run: DemoRun) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> DemoRun | None:
        return self._runs.get(run_id)

    def all_runs(self) -> list[DemoRun]:
        """Newest-first snapshot for read-only list views (Overview, Workflows,
        Approvals, Audit). Does not mutate or reorder the underlying registry."""

        return sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)

    def issue_receipt(
        self,
        run: DemoRun,
        *,
        esign_status: ReceiptESignStatus = ReceiptESignStatus.NOT_ATTEMPTED,
        foxit_identifier: str | None = None,
    ) -> ReceiptChainEntry:
        if run.result is None:
            raise ValueError("Cannot issue a receipt without a verification result")
        previous = self._last_receipt_sha256
        receipt = issue_decision_receipt(
            result=run.result,
            previous_receipt_sha256=previous,
            approval=run.profile_approval,
            esign_status=esign_status,
            foxit_identifier=foxit_identifier,
        )
        self._receipt_count += 1
        entry = ReceiptChainEntry(
            sequence=self._receipt_count,
            expected_previous_receipt_sha256=previous,
            receipt=receipt,
            approval=run.profile_approval,
            esign=receipt.esign,
        )
        run.receipt_history.append(entry)
        run.receipt_pdf_path = None
        run.receipt_pdf_hash = None
        self._last_receipt_sha256 = receipt.receipt_sha256
        return entry

    def reset(self, *, artifacts_directory: Path) -> int:
        """Clear only in-memory demo runs/receipts and their temporary artifacts.

        Never touches credentials, source code, policy files, or external Foxit
        state. Only removes files under ``artifacts_directory`` whose names are
        derived from server-generated run IDs, so this is bounded and safe.
        """

        cleared_run_ids = list(self._runs)
        for run_id in cleared_run_ids:
            run = self._runs[run_id]
            for suffix in (".pdf", ".txt"):
                candidate = artifacts_directory / f"{run_id}{suffix}"
                if candidate.is_file():
                    candidate.unlink(missing_ok=True)
            if run.receipt_pdf_path is not None and run.receipt_pdf_path.is_file():
                run.receipt_pdf_path.unlink(missing_ok=True)
        self._runs.clear()
        self._last_receipt_sha256 = None
        self._receipt_count = 0
        return len(cleared_run_ids)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; frame-src 'self'; object-src 'self'; "
                    "base-uri 'none'; form-action 'self'"
                )
                if scope.get("path", "").startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self._app(scope, receive, send_with_headers)


def create_app(
    *,
    demo_service: Phase3DemoService | None = None,
    approval_service: ApprovalSendService | None = None,
    signer_factory: Callable[[], Signer] | None = None,
    artifact_directory: Path | None = None,
    attack_runner: AttackRunner | None = None,
    receipt_pdf_generator: DecisionReceiptPdfGenerator | None = None,
    public_provider_factory: Callable[[DemoPreset], PublicEvidenceProvider]
    | None = None,
    public_semantic_engine_factory: Callable[[], SemanticEngine] | None = None,
) -> FastAPI:
    _validate_startup_configuration()
    service = demo_service or Phase3DemoService()
    human_approval_service = approval_service or ApprovalSendService(
        LiveFoxitESignSender()
    )
    recipient_factory = signer_factory or signer_from_env
    configured_artifacts = Path(
        os.getenv("CLAIMGATE_WEB_ARTIFACT_DIRECTORY", str(DEFAULT_ARTIFACT_DIRECTORY))
    )
    artifacts = (artifact_directory or configured_artifacts).resolve()
    security_lab = attack_runner or AttackRunner(artifacts / "attack-lab")
    audit_pdf_generator = receipt_pdf_generator or DecisionReceiptPdfGenerator(
        service.new_pdf_adapter
    )
    search_provider_factory = public_provider_factory or _public_provider_for_preset
    comparison_engine_factory = (
        public_semantic_engine_factory or _public_semantic_engine
    )
    registry = RunRegistry()
    users = UserStore()
    sessions = SessionStore()
    uploads = UploadStore(artifacts / "uploads")
    application = FastAPI(
        title="ClaimGate",
        description="Authorization infrastructure for AI agents performing irreversible actions.",
        version="0.1.0",
    )
    application.state.demo_service = service
    application.state.approval_service = human_approval_service
    application.state.run_registry = registry
    application.state.artifact_directory = artifacts
    application.state.attack_runner = security_lab
    application.state.receipt_pdf_generator = audit_pdf_generator
    application.state.replay_verifier = ReplayVerifier()
    application.state.public_provider_factory = search_provider_factory
    application.state.public_semantic_engine_factory = comparison_engine_factory
    application.state.users = users
    application.state.sessions = sessions
    application.state.uploads = uploads
    application.add_middleware(SecurityHeadersMiddleware)

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": (
                    "ClaimGate encountered an unexpected error and failed closed. Nothing "
                    "was authorized or sent."
                ),
                "failed_closed": True,
            },
        )

    def _read_template(name: str) -> HTMLResponse:
        html = (WEB_DIRECTORY / "templates" / name).read_text(encoding="utf-8")
        return HTMLResponse(html)

    def _current_user(request: Request):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        user_id = sessions.user_id_for(token)
        if user_id is None:
            return None
        return users.get_by_id(user_id)

    def _require_page_session(request: Request):
        """Gate for the /app/* product shell only. Every other existing route
        (including the compatibility aliases below) is left exactly as it was
        before this phase — unauthenticated, since nothing protected them
        before either. See auth.py's module docstring for what this session
        layer is and is not."""

        user = _current_user(request)
        if user is None:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        return None

    # --- Public marketing + auth pages -----------------------------------

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def landing_page() -> HTMLResponse:
        return _read_template("landing.html")

    @application.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page() -> HTMLResponse:
        return _read_template("login.html")

    @application.get("/signup", response_class=HTMLResponse, include_in_schema=False)
    async def signup_page() -> HTMLResponse:
        return _read_template("signup.html")

    @application.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
    async def forgot_password_page() -> HTMLResponse:
        return _read_template("forgot_password.html")

    # --- Authenticated product shell --------------------------------------
    # /app and every /app/* route require a session; unauthenticated requests
    # are redirected to /login. The bare (unprefixed) paths below are kept
    # only for backward compatibility with links from earlier phases and
    # remain unauthenticated, exactly as they always were.

    @application.get("/app", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/workflows", response_class=HTMLResponse, include_in_schema=False)
    @application.get(
        "/app/workflows/{run_id}", response_class=HTMLResponse, include_in_schema=False
    )
    @application.get("/app/approvals", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/evidence", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/policies", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/audit", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/integrations", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/security", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/app/settings", response_class=HTMLResponse, include_in_schema=False)
    async def app_shell_page(request: Request, run_id: str | None = None):
        redirect = _require_page_session(request)
        if redirect is not None:
            return redirect
        return _read_template("index.html")

    @application.get("/workflows", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/workflows/{run_id}", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/approvals", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/evidence", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/policies", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/audit", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/integrations", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/security", response_class=HTMLResponse, include_in_schema=False)
    @application.get("/settings", response_class=HTMLResponse, include_in_schema=False)
    async def platform_page_compat(run_id: str | None = None) -> HTMLResponse:
        return _read_template("index.html")

    @application.get("/static/brand/{asset_name}", include_in_schema=False)
    async def brand_asset(asset_name: str) -> Response:
        allowed_assets = {
            "apple-touch-icon.png",
            "claimgate-logo-source.png",
            "claimgate-logo.png",
            "claimgate-mark.png",
            "favicon-32.png",
            "favicon-64.png",
        }
        if asset_name not in allowed_assets:
            raise HTTPException(status_code=404, detail="Brand asset not found")
        content = (WEB_DIRECTORY / "static" / "brand" / asset_name).read_bytes()
        return Response(content=content, media_type="image/png")

    @application.get("/static/{asset_name}", include_in_schema=False)
    async def static_asset(asset_name: str) -> Response:
        media_types = {
            "app.css": "text/css",
            "app.js": "text/javascript",
            "landing.css": "text/css",
            "landing.js": "text/javascript",
            "auth.css": "text/css",
            "auth.js": "text/javascript",
        }
        media_type = media_types.get(asset_name)
        if media_type is None:
            raise HTTPException(status_code=404, detail="Static asset not found")
        content = (WEB_DIRECTORY / "static" / asset_name).read_bytes()
        return Response(content=content, media_type=media_type)

    @application.get("/api/presets")
    async def list_presets() -> dict[str, object]:
        return {"presets": service.list_presets()}

    @application.get("/api/policy-profiles")
    async def list_policy_profiles() -> dict[str, object]:
        return {"profiles": service.list_policy_profiles()}

    @application.get("/api/actions/catalog")
    async def actions_catalog() -> dict[str, object]:
        return {
            "capabilities": [
                {
                    "action_type": capability.action_type.value,
                    "supported": capability.supported,
                    "live_execution": capability.live_execution,
                    "adapter": capability.adapter,
                }
                for capability in CAPABILITY_REGISTRY.values()
            ]
        }

    @application.get("/api/attack-lab")
    async def attack_lab_catalog() -> dict[str, object]:
        return {
            "scenarios": [
                scenario.model_dump(mode="json") for scenario in security_lab.scenarios
            ],
            "security_invariants": [
                assertion.model_dump(mode="json")
                for assertion in security_lab.security_invariants()
            ],
            "execution_boundary": (
                "Controlled local adapters only; no document or e-signature network calls and "
                "no live execution for any simulated-only action type"
            ),
        }

    @application.post("/api/attack-lab/{scenario_id}/run")
    async def run_attack(scenario_id: AttackScenarioId) -> dict[str, object]:
        result = await security_lab.run(scenario_id)
        return result.model_dump(mode="json")

    @application.get("/api/diagnostics")
    async def diagnostics() -> dict[str, object]:
        return _diagnostics_snapshot()

    # --- Auth: lightweight, local/dev session endpoints (see auth.py) -----

    def _set_session_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
            path="/",
        )

    @application.post("/api/auth/signup", status_code=status.HTTP_201_CREATED)
    async def signup(payload: SignupRequest, response: Response) -> dict[str, object]:
        if payload.password != payload.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        if not is_valid_email(payload.email):
            raise HTTPException(status_code=400, detail="Enter a valid email address")
        try:
            user = users.create(
                full_name=payload.full_name,
                email=payload.email,
                workspace_name=payload.workspace_name,
                password=payload.password,
            )
        except EmailAlreadyRegisteredError as exc:
            raise HTTPException(status_code=409, detail="This email is already registered") from exc
        token = sessions.create(user.user_id)
        _set_session_cookie(response, token)
        return {"user": user.public_profile()}

    @application.post("/api/auth/login")
    async def login(payload: LoginRequest, response: Response) -> dict[str, object]:
        user = users.authenticate(email=payload.email, password=payload.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = sessions.create(user.user_id)
        _set_session_cookie(response, token)
        return {"user": user.public_profile()}

    @application.post("/api/auth/logout")
    async def logout(request: Request, response: Response) -> dict[str, object]:
        sessions.destroy(request.cookies.get(SESSION_COOKIE_NAME))
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return {"status": "LOGGED_OUT"}

    @application.get("/api/auth/session")
    async def session_info(request: Request) -> dict[str, object]:
        user = _current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Not signed in")
        return {"user": user.public_profile()}

    @application.post("/api/auth/forgot-password")
    async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, object]:
        # Deliberately returns the same response whether or not the email is
        # registered (does not leak account existence) and never sends real
        # email — this build has no outbound mail integration. See the
        # honesty note on the forgot-password page itself.
        return {
            "status": "ACKNOWLEDGED",
            "message": (
                "If an account exists for this email, a production deployment would send "
                "recovery instructions. This build does not send real email."
            ),
        }

    # --- Uploads: controlled local storage for the workflow-creation flow -

    def _require_api_session(request: Request):
        user = _current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in to continue")
        return user

    @application.post("/api/uploads", status_code=status.HTTP_201_CREATED)
    async def create_upload(
        request: Request,
        kind: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        user = _require_api_session(request)
        if kind not in {"artifact", "evidence"}:
            raise HTTPException(status_code=400, detail="kind must be 'artifact' or 'evidence'")
        content = await file.read()
        try:
            record = uploads.save(
                kind=kind,
                filename=file.filename or "upload",
                content=content,
                owner_user_id=user.user_id,
            )
        except UploadRejectedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return record.public_dict()

    @application.get("/api/uploads")
    async def list_uploads(request: Request) -> dict[str, object]:
        user = _require_api_session(request)
        owned = uploads.list_for_owner(user.user_id)
        return {"uploads": [record.public_dict() for record in owned]}

    @application.delete("/api/uploads/{upload_id}")
    async def delete_upload(upload_id: str, request: Request) -> dict[str, object]:
        user = _require_api_session(request)
        removed = uploads.delete(upload_id, owner_user_id=user.user_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Upload not found")
        return {"status": "DELETED", "upload_id": upload_id}

    @application.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(
        payload: StartRunRequest,
        background_tasks: BackgroundTasks,
        request: Request,
    ) -> dict[str, str]:
        _require_api_session(request)
        run_id = secrets.token_hex(12)
        output_path = artifacts / f"{run_id}.pdf"
        run = DemoRun(
            run_id=run_id,
            preset=payload.preset,
            output_path=output_path,
            policy_profile=payload.policy_profile,
        )
        registry.add(run)
        background_tasks.add_task(_execute_run, service, registry, run)
        return {
            "run_id": run_id,
            "status_url": f"/api/runs/{run_id}",
        }

    @application.post("/api/runs/document", status_code=status.HTTP_202_ACCEPTED)
    async def start_document_run(
        payload: StartDocumentRunRequest,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        """Start a real workflow from a document the user uploaded — the
        agreement's claims are extracted from the actual file and checked
        against actual, user-supplied evidence. No fixed preset is involved."""

        user = _require_api_session(request)
        artifact_record = uploads.get(payload.artifact_upload_id)
        if (
            artifact_record is None
            or artifact_record.owner_user_id != user.user_id
            or artifact_record.kind != "artifact"
        ):
            raise HTTPException(status_code=404, detail="Uploaded document not found")

        evidence_specs: list[_EvidenceSpec] = []
        for index, item in enumerate(payload.evidence):
            source_id = f"evidence-{index + 1}"
            if item.upload_id:
                evidence_record = uploads.get(item.upload_id)
                if evidence_record is None or evidence_record.owner_user_id != user.user_id:
                    raise HTTPException(status_code=404, detail="Evidence upload not found")
                evidence_specs.append(
                    _EvidenceSpec(
                        source_id=source_id,
                        title=item.title,
                        upload_path=evidence_record.path,
                    )
                )
            elif item.text and item.text.strip():
                evidence_specs.append(
                    _EvidenceSpec(source_id=source_id, title=item.title, text=item.text.strip())
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Each evidence item needs an uploaded file or pasted text",
                )

        run_id = secrets.token_hex(12)
        output_path = artifacts / f"{run_id}.pdf"
        run = DemoRun(
            run_id=run_id,
            output_path=output_path,
            policy_profile=payload.policy_profile,
            is_document_run=True,
            owner_user_id=user.user_id,
            source_filename=artifact_record.original_filename,
        )
        registry.add(run)
        background_tasks.add_task(
            _execute_document_run,
            service,
            registry,
            run,
            artifact_record.path,
            evidence_specs,
        )
        return {
            "run_id": run_id,
            "status_url": f"/api/runs/{run_id}",
        }

    @application.get("/api/runs")
    async def list_runs(request: Request) -> dict[str, object]:
        """Read-only, newest-first projection of existing run state for the
        Overview, Workflows, Approvals, and Audit list views. Adds no new
        decision or authorization semantics — every field here is already
        computed by _serialize_result for the single-run endpoint."""

        _require_api_session(request)
        return {"runs": [_serialize_run_summary(run) for run in registry.all_runs()]}

    @application.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, object]:
        _require_api_session(request)
        run = registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Demo run not found")
        return _serialize_run(run)

    @application.post("/api/runs/{run_id}/approve-and-send")
    async def approve_and_send(
        run_id: str, payload: ApprovalRequest, request: Request
    ) -> dict[str, object]:
        _require_api_session(request)
        if not payload.confirmed:
            raise HTTPException(
                status_code=400,
                detail="Explicit human confirmation is required",
            )
        run = registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Demo run not found")

        async with run.send_lock:
            if run.send_attempted:
                raise HTTPException(
                    status_code=409,
                    detail="A send has already been attempted for this run",
                )
            if run.status is not RunStatus.COMPLETE or run.result is None:
                raise HTTPException(status_code=409, detail="Verification is not complete")
            if run.result.workflow.state is not WorkflowState.READY_FOR_APPROVAL:
                raise HTTPException(
                    status_code=409,
                    detail="Only READY_FOR_APPROVAL runs may be sent",
                )

            try:
                signer: Signer = recipient_factory()
            except Exception as exc:
                LOGGER.exception("E-signature recipient configuration is invalid")
                raise HTTPException(
                    status_code=503,
                    detail="E-signature recipient is not configured",
                ) from exc

            run.send_attempted = True
            try:
                outcome = human_approval_service.approve_and_send(
                    result=run.result,
                    signer=signer,
                    approved_by="Phase 5 demo human",
                    confirmed=True,
                )
            except ApprovalBoundaryError as exc:
                run.send_error = str(exc)
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            run.send_state = outcome.state
            run.esign_folder_id = outcome.folder_id
            run.send_error = outcome.error
            run.profile_approval = outcome.approval
            run.action_approval = build_action_approval_record(
                build_sign_document_action(run.result), approved_by="Phase 5 demo human"
            )
            registry.issue_receipt(
                run,
                esign_status=(
                    ReceiptESignStatus.SENT
                    if outcome.state is WorkflowState.SENT
                    else ReceiptESignStatus.SEND_FAILED
                ),
                foxit_identifier=outcome.folder_id,
            )
            return _serialize_send(run)

    @application.get("/api/runs/{run_id}/pdf")
    async def get_pdf(run_id: str, request: Request) -> Response:
        _require_api_session(request)
        run = registry.get(run_id)
        if (
            run is None
            or run.status is not RunStatus.COMPLETE
            or run.result is None
            or not run.result.pdf_path.is_file()
        ):
            raise HTTPException(status_code=404, detail="Verified PDF is not available")
        return Response(
            content=run.result.pdf_path.read_bytes(),
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="claimgate-agreement.pdf"',
            },
        )

    @application.get("/api/runs/{run_id}/receipt.json")
    async def download_receipt_json(run_id: str, request: Request) -> Response:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        receipt = run.receipt_history[-1].receipt
        return Response(
            content=canonical_receipt_json(receipt).encode("utf-8"),
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": (
                    f'attachment; filename="claimgate-{run_id}-receipt.json"'
                ),
            },
        )

    @application.post("/api/runs/{run_id}/receipt/verify")
    async def verify_run_receipt(run_id: str, request: Request) -> dict[str, object]:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        return _verify_latest_receipt(run).model_dump(mode="json")

    @application.post("/api/runs/{run_id}/replay")
    async def replay_historical_receipt(
        run_id: str, payload: ReplayApiRequest, request: Request
    ) -> dict[str, object]:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        entry = next(
            (
                candidate
                for candidate in run.receipt_history
                if candidate.receipt.receipt_sha256 == payload.receipt_sha256
            ),
            None,
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail="Historical receipt is not available for this run",
            )
        replay_request = ReplayRequest(
            run_id=run_id,
            receipt_sha256=payload.receipt_sha256,
            preset=payload.preset,
        )
        snapshot = apply_replay_preset(
            _capture_replay_snapshot(run, entry), payload.preset
        )
        replay_result = application.state.replay_verifier.verify(
            request=replay_request,
            receipt=entry.receipt,
            snapshot=snapshot,
        )
        return replay_result.model_dump(mode="json")

    @application.post("/api/runs/{run_id}/claims/{claim_id}/public-evidence")
    async def search_public_evidence(
        run_id: str, claim_id: str, request: Request
    ) -> dict[str, object]:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        async with run.public_evidence_lock:
            if run.send_attempted or run.profile_approval is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Public evidence cannot change an approved or sent run",
                )
            if claim_id in run.public_evidence_attempted:
                raise HTTPException(
                    status_code=409,
                    detail="Public evidence search was already attempted for this claim",
                )
            result = run.result
            if result is None:
                raise HTTPException(status_code=409, detail="Verification is not complete")
            claim = next(
                (item for item in result.extracted_claims if item.claim_id == claim_id),
                None,
            )
            if claim is None:
                raise HTTPException(status_code=404, detail="Claim is not part of this run")
            fact_type = _public_fact_type(claim.category)
            if fact_type is None:
                raise HTTPException(
                    status_code=409,
                    detail="This private claim category is not eligible for public search",
                )
            try:
                search_provider = search_provider_factory(run.preset)
                comparison_engine = comparison_engine_factory()
            except Exception as exc:
                LOGGER.exception("Public evidence provider configuration is invalid")
                raise HTTPException(
                    status_code=503,
                    detail="Public evidence provider is not configured",
                ) from exc
            run.public_evidence_attempted.add(claim_id)
            enrichment = await PublicEvidenceService(
                search_provider
            ).enrich_result(
                result=result,
                claim_id=claim_id,
                fact_type=fact_type,
                semantic_engine=comparison_engine,
            )
            run.public_discoveries[claim_id] = enrichment.discovery
            if enrichment.reevaluated:
                run.result = enrichment.result
                registry.issue_receipt(run)
            serialized = _serialize_result(run, run.result)
            serialized["public_evidence_update"] = {
                "claim_id": claim_id,
                "previous_status": enrichment.previous_status.value,
                "current_status": enrichment.current_status.value,
                "reevaluated": enrichment.reevaluated,
                "discovery": enrichment.discovery.model_dump(mode="json"),
            }
            return serialized

    @application.post("/api/runs/{run_id}/receipt/pdf")
    async def generate_receipt_pdf(run_id: str, request: Request) -> dict[str, str]:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        async with run.receipt_lock:
            receipt = run.receipt_history[-1].receipt
            output_path = artifacts / "receipts" / f"{receipt.receipt_sha256}.pdf"
            try:
                generated = await audit_pdf_generator.generate(receipt, output_path)
            except Exception as exc:
                LOGGER.exception("Decision Receipt PDF generation failed for %s", run_id)
                raise HTTPException(
                    status_code=502,
                    detail="Decision Receipt PDF generation failed",
                ) from exc
            run.receipt_pdf_path = generated.resolve()
            run.receipt_pdf_hash = receipt.receipt_sha256
        return {"pdf_url": f"/api/runs/{run_id}/receipt.pdf"}

    @application.get("/api/runs/{run_id}/receipt.pdf")
    async def get_receipt_pdf(run_id: str, request: Request) -> Response:
        _require_api_session(request)
        run = _require_receipt_run(registry, run_id)
        latest_hash = run.receipt_history[-1].receipt.receipt_sha256
        if (
            run.receipt_pdf_path is None
            or run.receipt_pdf_hash != latest_hash
            or not run.receipt_pdf_path.is_file()
        ):
            raise HTTPException(status_code=404, detail="Decision Receipt PDF is not available")
        return Response(
            content=run.receipt_pdf_path.read_bytes(),
            media_type="application/pdf",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="claimgate-decision-receipt.pdf"',
            },
        )

    return application


def _require_receipt_run(registry: RunRegistry, run_id: str) -> DemoRun:
    run = registry.get(run_id)
    if (
        run is None
        or run.status is not RunStatus.COMPLETE
        or run.result is None
        or not run.receipt_history
    ):
        raise HTTPException(status_code=404, detail="Decision Receipt is not available")
    return run


def _verify_latest_receipt(run: DemoRun):
    entry = run.receipt_history[-1]
    result = run.result
    if result is None:
        raise ValueError("Receipt run has no result")
    approval = run.profile_approval if entry.receipt.approval.occurred else None
    return verify_receipt(
        entry.receipt,
        ReceiptVerificationContext(
            pdf_path=result.pdf_path,
            evidence=result.evidence,
            policy_profile=result.selected_policy_profile,
            approval=approval,
            expected_previous_receipt_sha256=(
                entry.expected_previous_receipt_sha256
            ),
            evidence_documents=result.evidence_documents,
        ),
    )


def _capture_replay_snapshot(
    run: DemoRun, entry: ReceiptChainEntry
):
    result = run.result
    if result is None:
        raise ValueError("Replay run has no verification result")
    return capture_artifact_snapshot(
        pdf_path=result.pdf_path,
        evidence=result.evidence,
        policy_profile=result.selected_policy_profile,
        approval=entry.approval,
        esign=entry.esign,
        expected_previous_receipt_sha256=entry.expected_previous_receipt_sha256,
        action=build_sign_document_action(result),
        evidence_documents=result.evidence_documents,
    )


async def _execute_run(
    service: Phase3DemoService, registry: RunRegistry, run: DemoRun
) -> None:
    try:
        run.output_path.parent.mkdir(parents=True, exist_ok=True)
        run.result = await service.run(
            run_id=run.run_id,
            preset=run.preset,
            policy_profile=run.policy_profile,
            output_path=run.output_path,
            progress_observer=run.observe,
        )
        run.finish_timing()
        registry.issue_receipt(run)
        run.status = RunStatus.COMPLETE
    except Exception:
        LOGGER.exception("ClaimGate demo run %s failed", run.run_id)
        run.finish_timing()
        run.status = RunStatus.FAILED
        run.public_error = (
            "Verification failed and the run did not reach a decision. The deterministic "
            "safety system failed closed: nothing was authorized or sent. Check the server "
            "log and configuration."
        )


@dataclass(frozen=True)
class _EvidenceSpec:
    source_id: str
    title: str
    text: str | None = None
    upload_path: Path | None = None


async def _execute_document_run(
    service: Phase3DemoService,
    registry: RunRegistry,
    run: DemoRun,
    artifact_path: Path,
    evidence_specs: list[_EvidenceSpec],
) -> None:
    try:
        run.output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_adapter = service.new_pdf_adapter()
        evidence_documents: list[EvidenceDocument] = []
        for spec in evidence_specs:
            if spec.text is not None:
                evidence_documents.append(
                    EvidenceIngestor.plain_text(
                        source_id=spec.source_id, title=spec.title, text=spec.text
                    )
                )
                continue
            assert spec.upload_path is not None
            if spec.upload_path.suffix.lower() == ".pdf":
                extracted_text_path = spec.upload_path.with_suffix(".evidence.txt")
                extracted_text = await pdf_adapter.extract_text_from_pdf(
                    spec.upload_path, extracted_text_path
                )
            else:
                extracted_text = spec.upload_path.read_text(
                    encoding="utf-8", errors="replace"
                )
            evidence_documents.append(
                EvidenceIngestor.pdf_derived_text(
                    source_id=spec.source_id,
                    title=spec.title,
                    extracted_text=extracted_text,
                )
            )

        run.result = await service.run_from_document(
            run_id=run.run_id,
            artifact_path=artifact_path,
            evidence_documents=evidence_documents,
            policy_profile=run.policy_profile,
            output_path=run.output_path,
            progress_observer=run.observe,
        )
        run.finish_timing()
        registry.issue_receipt(run)
        run.status = RunStatus.COMPLETE
    except RealDocumentReviewUnavailableError as exc:
        LOGGER.warning("ClaimGate document run %s could not start: %s", run.run_id, exc)
        run.finish_timing()
        run.status = RunStatus.FAILED
        run.public_error = str(exc)
    except Exception:
        LOGGER.exception("ClaimGate document run %s failed", run.run_id)
        run.finish_timing()
        run.status = RunStatus.FAILED
        run.public_error = (
            "Verification failed and the run did not reach a decision. The deterministic "
            "safety system failed closed: nothing was authorized or sent. Check the server "
            "log and configuration."
        )


def _serialize_run_summary(run: DemoRun) -> dict[str, object]:
    """Lightweight, list-view projection of a run. Every value is read from
    fields _serialize_run/_serialize_result already compute for the single-run
    endpoint — this adds no new decision logic, only a smaller shape for
    Overview/Workflows/Approvals/Audit tables."""

    summary: dict[str, object] = {
        "run_id": run.run_id,
        "preset": run.preset.value if run.preset is not None else "uploaded_document",
        "preset_title": (
            preset_definition(run.preset).title
            if run.preset is not None
            else (run.source_filename or "Uploaded document")
        ),
        "policy_profile": run.policy_profile.value,
        "status": run.status.value,
        "action_type": "SIGN_DOCUMENT",
        "integration": "E-Signature",
        "created_at": run.created_at.isoformat(),
        "decision": None,
        "workflow_state": None,
        "risk": None,
        "pdf_sha256": None,
        "policy_profile_name": None,
        "approval_available": False,
        "send_attempted": run.send_attempted,
        "send_state": run.send_state.value if run.send_state else None,
        "latest_receipt_sha256": (
            run.receipt_history[-1].receipt.receipt_sha256 if run.receipt_history else None
        ),
    }
    result = run.result
    if result is not None:
        is_ready = result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
        summary.update(
            {
                "decision": "READY_FOR_HUMAN_APPROVAL" if is_ready else "SIGNING_BLOCKED",
                "workflow_state": result.workflow.state.value,
                "risk": build_sign_document_action(result).risk.value,
                "pdf_sha256": result.decision.pdf_sha256,
                "policy_profile_name": result.selected_policy_profile.name,
                "approval_available": (
                    is_ready
                    and result.workflow.state is WorkflowState.READY_FOR_APPROVAL
                    and not run.send_attempted
                ),
            }
        )
    return summary


def _serialize_run(run: DemoRun) -> dict[str, object]:
    response: dict[str, object] = {
        "run_id": run.run_id,
        "preset": run.preset.value if run.preset is not None else "uploaded_document",
        "preset_title": (
            preset_definition(run.preset).title
            if run.preset is not None
            else (run.source_filename or "Uploaded document")
        ),
        "policy_profile": run.policy_profile.value,
        "status": run.status.value,
        "current_progress": (
            run.progress_history[-1].value if run.progress_history else None
        ),
        "progress": _serialize_progress(run),
        "error": run.public_error,
    }
    if run.result is not None:
        response["result"] = _serialize_result(run, run.result)
    return response


def _serialize_progress(run: DemoRun) -> list[dict[str, str]]:
    history = list(run.progress_history)
    current_index = len(history) - 1
    skip = (
        Phase3Progress.READING_DOCUMENT
        if not run.is_document_run
        else Phase3Progress.GENERATING_DOCUMENT
    )
    steps = []
    for progress in Phase3Progress:
        if progress is skip:
            continue
        if run.status is RunStatus.COMPLETE:
            step_status = "complete"
        elif progress in history:
            step_status = "active" if history.index(progress) == current_index else "complete"
        else:
            step_status = "pending"
        steps.append(
            {
                "id": progress.value,
                "label": PROGRESS_LABELS[progress],
                "status": step_status,
            }
        )
    return steps


def _serialize_result(run: DemoRun, result: Phase3Result) -> dict[str, object]:
    verification_by_claim = {
        verification.claim_id: verification for verification in result.verification.results
    }
    evidence_by_id = {source.source_id: source for source in result.evidence}
    evidence_documents_by_id = {
        document.source.source_id: document for document in result.evidence_documents
    }
    claims = []
    for claim in result.extracted_claims:
        verification = verification_by_claim.get(claim.claim_id)
        source = (
            evidence_by_id.get(verification.evidence_id)
            if verification is not None and verification.evidence_id is not None
            else None
        )
        claims.append(
            {
                "claim_id": claim.claim_id,
                "category": claim.category.value,
                "value": claim.normalized_value,
                "critical": claim.critical,
                "source_text": claim.source_text,
                "status": verification.status.value if verification else "FAILED",
                "evidence_quote": verification.quotation if verification else None,
                "evidence_source_id": source.source_id if source else None,
                "evidence_source_title": source.title if source else None,
                "evidence_authority": (
                    evidence_documents_by_id[source.source_id].authority.value
                    if source
                    else None
                ),
                "public_search": {
                    "eligible": (
                        verification is not None
                        and verification.status
                        in {
                            VerificationStatus.UNSUPPORTED,
                            VerificationStatus.UNCERTAIN,
                        }
                        and _public_fact_type(claim.category) is not None
                        and claim.claim_id not in run.public_evidence_attempted
                        and not run.send_attempted
                        and run.profile_approval is None
                    ),
                    "attempted": claim.claim_id in run.public_evidence_attempted,
                    "url": (
                        f"/api/runs/{run.run_id}/claims/{claim.claim_id}/public-evidence"
                    ),
                    "discovery": (
                        run.public_discoveries[claim.claim_id].model_dump(mode="json")
                        if claim.claim_id in run.public_discoveries
                        else None
                    ),
                },
            }
        )

    is_ready = result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    blockers = [
        {
            "code": blocker.code,
            "message": blocker.message,
            "claim_id": blocker.claim_id,
            "explanation": _blocker_explanation(blocker.claim_id, result),
        }
        for blocker in result.decision.blockers
    ]
    return {
        "decision": "READY_FOR_HUMAN_APPROVAL" if is_ready else "SIGNING_BLOCKED",
        "decision_label": (
            "READY FOR HUMAN APPROVAL" if is_ready else "SIGNING BLOCKED"
        ),
        "claims": claims,
        "evidence_graph": _serialize_evidence_graph(result),
        "policy_evaluation": {
            "baseline": (
                "PASS"
                if result.baseline_decision.outcome
                is PolicyOutcome.READY_FOR_APPROVAL
                else "BLOCK"
            ),
            "profile": result.profile_decision.outcome.value,
            "final": "READY" if is_ready else "BLOCKED",
            "profile_blockers": [
                {
                    "code": blocker.code,
                    "message": blocker.message,
                    "category": blocker.category.value if blocker.category else None,
                    "claim_id": blocker.claim_id,
                }
                for blocker in result.profile_decision.blockers
            ],
        },
        "blockers": blockers,
        "pdf_url": f"/api/runs/{run.run_id}/pdf",
        "approval_available": (
            is_ready
            and result.workflow.state is WorkflowState.READY_FOR_APPROVAL
            and not run.send_attempted
        ),
        "send": _serialize_send(run),
        "receipt": _serialize_receipt(run),
        "audit_history": _serialize_audit_history(run),
        "action": _serialize_action(run, result),
        "timings": _serialize_timings(run),
        "audit": {
            "pdf_sha256": result.decision.pdf_sha256,
            "evidence_sha256": result.decision.evidence_sha256,
            "policy_version": result.decision.policy_version,
            "baseline_policy_version": result.baseline_decision.policy_version,
            "selected_profile": result.selected_policy_profile.id,
            "selected_profile_name": result.selected_policy_profile.name,
            "policy_profile_hash": result.selected_policy_profile.profile_hash,
            "profile_specific_blockers": [
                blocker.message for blocker in result.profile_decision.blockers
            ],
            "workflow_state": result.workflow.state.value,
        },
    }


def _serialize_receipt(run: DemoRun) -> dict[str, object] | None:
    if not run.receipt_history:
        return None
    entry = run.receipt_history[-1]
    receipt = entry.receipt
    return {
        "receipt_id": f"CG-{receipt.receipt_sha256[:12].upper()}",
        "receipt_sha256": receipt.receipt_sha256,
        "receipt_version": receipt.receipt_version,
        "sequence": entry.sequence,
        "previous_receipt_sha256": receipt.previous_receipt_sha256,
        "final_decision": receipt.final_decision.value,
        "workflow_state": receipt.workflow_state.value,
        "canonical_json_url": f"/api/runs/{run.run_id}/receipt.json",
        "verify_url": f"/api/runs/{run.run_id}/receipt/verify",
        "generate_pdf_url": f"/api/runs/{run.run_id}/receipt/pdf",
        "pdf_url": (
            f"/api/runs/{run.run_id}/receipt.pdf"
            if run.receipt_pdf_hash == receipt.receipt_sha256
            else None
        ),
        "structured": receipt.model_dump(mode="json"),
    }


def _serialize_audit_history(run: DemoRun) -> dict[str, object] | None:
    if run.result is None or not run.receipt_history:
        return None
    receipts = tuple(entry.receipt for entry in run.receipt_history)
    timeline = build_audit_timeline(
        run_id=run.run_id,
        run_created_at=run.created_at,
        receipts=receipts,
    )
    return {
        "original_final_decision": receipts[0].final_decision.value,
        "current_workflow_state": run.result.workflow.state.value,
        "policy_profile_id": run.result.selected_policy_profile.id,
        "pdf_sha256": run.result.decision.pdf_sha256,
        "evidence_sha256": run.result.decision.evidence_sha256,
        "receipts": [
            {
                "sequence": entry.sequence,
                "receipt_sha256": entry.receipt.receipt_sha256,
                "decision": entry.receipt.final_decision.value,
                "workflow_state": entry.receipt.workflow_state.value,
                "created_at": entry.receipt.created_at.isoformat(),
            }
            for entry in run.receipt_history
        ],
        "timeline": [event.model_dump(mode="json") for event in timeline],
        "replay_presets": [preset.value for preset in ReplayPreset],
        "replay_url": f"/api/runs/{run.run_id}/replay",
    }


def _serialize_evidence_graph(result: Phase3Result) -> dict[str, object] | None:
    graph = result.evidence_graph
    if graph is None:
        return None
    summary = graph.summary
    evidence_by_id = {source.source_id: source for source in graph.evidence}
    return {
        "claims": [
            {
                "claim_id": claim.claim_id,
                "category": claim.category.value,
                "value": claim.normalized_value,
                "source_text": claim.source_text,
                "critical": claim.critical,
            }
            for claim in graph.claims
        ],
        "evidence": [
            {
                "source_id": source.source_id,
                "title": source.title,
                "kind": source.kind,
                "authority": source.authority.value,
                "authoritative": source.authority.is_authoritative,
                "public": source.provenance is not None,
                "provenance": (
                    {
                        "provider": source.provenance.provider,
                        "source_url": source.provenance.source_url,
                        "domain": source.provenance.domain,
                        "retrieved_at": source.provenance.retrieved_at.isoformat(),
                        "query": source.provenance.query,
                        "source_type": source.provenance.source_type.value,
                    }
                    if source.provenance is not None
                    else None
                ),
            }
            for source in graph.evidence
        ],
        "edges": [
            {
                "edge_id": edge.edge_id,
                "claim_id": edge.claim_id,
                "evidence_id": edge.evidence_id,
                "evidence_title": evidence_by_id[edge.evidence_id].title,
                "relationship": edge.relationship.value,
                "quotation": edge.quotation,
                "authority": evidence_by_id[edge.evidence_id].authority.value,
                "public": evidence_by_id[edge.evidence_id].provenance is not None,
            }
            for edge in graph.edges
        ],
        "summary": {
            "material_claims": len(graph.claims),
            "evidence_sources": len(graph.evidence),
            "support_count": summary.support_count,
            "conflict_count": summary.conflict_count,
            "uncertain_count": summary.uncertain_count,
            "authoritative_support_count": summary.authoritative_support_count,
            "authoritative_conflict_count": summary.authoritative_conflict_count,
        },
    }


def _serialize_action(run: DemoRun, result: Phase3Result) -> dict[str, object]:
    action = build_sign_document_action(result)
    decision = authorize_action(action)
    return {
        "action_id": action.action_id,
        "action_type": action.action_type.value,
        "action_sha256": action_sha256(action),
        "target": action.target,
        "risk": action.risk.value,
        "description": action.description,
        "parameters": action.parameters,
        "execution_capability": {
            "adapter": decision.execution_capability.adapter,
            "live_execution": decision.execution_capability.live_execution,
        },
        "authorization_outcome": decision.outcome.value,
        "authorization_blockers": [
            {"code": blocker.code, "message": blocker.message} for blocker in decision.blockers
        ],
        "approval": (
            {
                "approved_by": run.action_approval.approved_by,
                "approved_at": run.action_approval.approved_at.isoformat(),
                "valid": is_approval_valid(run.action_approval, action),
            }
            if run.action_approval is not None
            else None
        ),
    }


def _serialize_timings(run: DemoRun) -> dict[str, object]:
    stages = [
        {
            "id": progress.value,
            "label": PROGRESS_LABELS[progress],
            "duration_ms": run.stage_duration_ms.get(progress.value),
        }
        for progress in Phase3Progress
        if progress.value in run.stage_duration_ms
    ]
    total_ms = round(sum(stage["duration_ms"] for stage in stages), 1) if stages else None
    return {"stages": stages, "total_ms": total_ms}


def _serialize_send(run: DemoRun) -> dict[str, object]:
    return {
        "attempted": run.send_attempted,
        "state": run.send_state.value if run.send_state else None,
        "folder_id": run.esign_folder_id,
        "error": run.send_error,
    }


def _blocker_explanation(claim_id: str | None, result: Phase3Result) -> str:
    if claim_id is not None:
        claim = next(
            (item for item in result.extracted_claims if item.claim_id == claim_id),
            None,
        )
        verification = next(
            (item for item in result.verification.results if item.claim_id == claim_id),
            None,
        )
        if (
            claim is not None
            and claim.category.value == "money"
            and verification is not None
            and verification.status is VerificationStatus.CONFLICTING
            and verification.quotation
        ):
            document_value = _value_after_label(claim.source_text)
            evidence_value = _value_after_label(verification.quotation)
            evidence_document = next(
                (
                    document
                    for document in result.evidence_documents
                    if document.source.source_id == verification.evidence_id
                ),
                None,
            )
            evidence_description = (
                "the authoritative quote"
                if evidence_document is not None
                and evidence_document.authority.is_authoritative
                else (
                    evidence_document.source.title
                    if evidence_document is not None
                    else "the referenced evidence"
                )
            )
            return (
                f"Contract amount is {document_value} in the document but "
                f"{evidence_value} in {evidence_description}."
            )
    return next(
        (
            blocker.message
            for blocker in result.decision.blockers
            if blocker.claim_id == claim_id
        ),
        "Deterministic policy requirements were not satisfied.",
    )


def _value_after_label(value: str) -> str:
    _, separator, remainder = value.partition(":")
    return remainder.strip() if separator else value.strip()


def _public_fact_type(category: ClaimCategory) -> PublicFactType | None:
    if category is ClaimCategory.PARTY_IDENTITY:
        return PublicFactType.PARTY_IDENTITY
    if category is ClaimCategory.OTHER:
        return PublicFactType.CERTIFICATION_STATUS
    return None


def _public_provider_for_preset(preset: DemoPreset) -> PublicEvidenceProvider:
    provider_name = os.getenv(
        "CLAIMGATE_PUBLIC_EVIDENCE_PROVIDER", "scripted"
    ).lower()
    if provider_name == "serpapi":
        return SerpApiPublicEvidenceProvider.from_env()
    if provider_name != "scripted":
        raise ValueError(f"Unsupported public evidence provider: {provider_name}")

    def scripted_response(query) -> object:
        registry_source = preset is DemoPreset.PUBLIC_CERTIFICATION
        domain = "iafcertsearch.org" if registry_source else "certification-fans.example"
        title = (
            "Certification X registry record"
            if registry_source
            else "Certification enthusiast blog"
        )
        return {
            "provider": "scripted-public-search",
            "candidates": [
                {
                    "source_id": "scripted-search-result-1",
                    "title": title,
                    "url": f"https://{domain}/records/example-organization",
                    "domain": domain,
                    "snippet": query.normalized_claim,
                    "retrieved_at": datetime.now(timezone.utc),
                    "query": query.query,
                    "authority": "UNVERIFIED_EXTERNAL",
                    "provider": "scripted-public-search",
                    "provenance_metadata": {
                        "engine": "scripted",
                        "position": "1",
                    },
                }
            ],
        }

    return ScriptedPublicEvidenceProvider([scripted_response])


def _public_semantic_engine() -> SemanticEngine:
    provider_name = os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").lower()
    if provider_name == "openai":
        return SemanticEngine(OpenAIResponsesProvider.from_env())
    if provider_name != "scripted":
        raise ValueError(f"Unsupported semantic provider: {provider_name}")

    def comparison_response(request: StructuredRequest) -> object:
        results = []
        for claim in request.untrusted_data["claims"]:
            normalized = str(claim["normalized_value"]).casefold()
            for source in request.untrusted_data["evidence_sources"]:
                content = str(source["content"])
                quotation = content.split(PUBLIC_EVIDENCE_SNIPPET_MARKER, 1)[-1]
                supported = normalized in content.casefold()
                results.append(
                    {
                        "claim_id": claim["claim_id"],
                        "status": "SUPPORTED" if supported else "UNCERTAIN",
                        "evidence_id": source["source_id"],
                        "quotation": quotation,
                        "notes": (
                            "Public snippet contains the normalized claim"
                            if supported
                            else "Public snippet does not establish the normalized claim"
                        ),
                    }
                )
        return {"complete": True, "results": results}

    return SemanticEngine(ScriptedSemanticProvider([comparison_response]))


load_dotenv()
app = create_app()


def main() -> None:
    host = os.getenv("CLAIMGATE_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("CLAIMGATE_WEB_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
