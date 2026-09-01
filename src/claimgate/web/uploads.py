"""Controlled, local file upload storage for the workflow-creation flow.

Security rules enforced here (see Phase 17 spec):
  - The browser never supplies a filesystem path — only a filename and bytes.
  - Filenames are sanitized to a safe character set before touching disk.
  - Every stored file gets a server-generated id; the id, not client input,
    is what the rest of the app ever references.
  - Only a small extension allowlist is accepted.
  - A hard size cap is enforced.
  - Uploaded files are never executed, imported, or parsed as code.

Uploaded evidence is NOT wired into the deterministic verification engine —
it is stored and displayed as a record attachment only. Promoting evidence to
AUTHORITATIVE status still only happens through the existing, code-controlled
evidence bundles; a browser upload cannot change what the policy engine
trusts. Storage is a local directory on the demo host, not a production
document-management system — it is cleared by the same demo-reset path as
everything else in this in-memory build.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".txt"}
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejectedError(ValueError):
    """Raised for any client-supplied upload that fails validation."""


def sanitize_filename(raw_name: str) -> str:
    """Strips any directory component and unsafe characters. Never trusts the
    browser's path — only the base filename is kept, and only from a safe
    character set."""

    base_name = Path(raw_name).name.strip()
    if not base_name or base_name in {".", ".."}:
        raise UploadRejectedError("Filename is missing or invalid")
    cleaned = _UNSAFE_CHARS.sub("_", base_name)
    if not cleaned or cleaned.startswith("."):
        raise UploadRejectedError("Filename is missing or invalid")
    return cleaned[:180]


def validate_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        label = suffix or "(none)"
        raise UploadRejectedError(f"Unsupported file type '{label}'. Allowed: {allowed}")
    return suffix


@dataclass(frozen=True)
class UploadRecord:
    upload_id: str
    kind: str
    original_filename: str
    stored_filename: str
    size_bytes: int
    owner_user_id: str
    path: Path
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def public_dict(self) -> dict[str, object]:
        return {
            "upload_id": self.upload_id,
            "kind": self.kind,
            "filename": self.original_filename,
            "size_bytes": self.size_bytes,
            "uploaded_at": self.uploaded_at.isoformat(),
        }


class UploadStore:
    """In-memory registry over files written to `directory`. Process-local,
    exactly like `RunRegistry` — cleared by demo reset, not a persistence
    guarantee across restarts."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._records: dict[str, UploadRecord] = {}

    def save(
        self, *, kind: str, filename: str, content: bytes, owner_user_id: str
    ) -> UploadRecord:
        if len(content) > MAX_UPLOAD_BYTES:
            raise UploadRejectedError(
                f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit"
            )
        if not content:
            raise UploadRejectedError("File is empty")
        safe_name = sanitize_filename(filename)
        validate_extension(safe_name)
        upload_id = secrets.token_hex(12)
        stored_filename = f"{upload_id}__{safe_name}"
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self._directory / stored_filename
        destination.write_bytes(content)
        record = UploadRecord(
            upload_id=upload_id,
            kind=kind,
            original_filename=safe_name,
            stored_filename=stored_filename,
            size_bytes=len(content),
            owner_user_id=owner_user_id,
            path=destination,
        )
        self._records[upload_id] = record
        return record

    def list_for_owner(self, owner_user_id: str) -> list[UploadRecord]:
        return sorted(
            (r for r in self._records.values() if r.owner_user_id == owner_user_id),
            key=lambda r: r.uploaded_at,
            reverse=True,
        )

    def get(self, upload_id: str) -> UploadRecord | None:
        return self._records.get(upload_id)

    def delete(self, upload_id: str, *, owner_user_id: str) -> bool:
        record = self._records.get(upload_id)
        if record is None or record.owner_user_id != owner_user_id:
            return False
        record.path.unlink(missing_ok=True)
        del self._records[upload_id]
        return True

    def reset(self) -> int:
        count = len(self._records)
        for record in list(self._records.values()):
            record.path.unlink(missing_ok=True)
        self._records.clear()
        return count
