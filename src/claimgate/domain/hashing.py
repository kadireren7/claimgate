"""Canonical SHA-256 helpers used by verification and approval bindings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from claimgate.domain.models import EvidenceSource


def pdf_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def evidence_sha256(sources: Iterable[EvidenceSource]) -> str:
    canonical_sources = [
        {
            "source_id": source.source_id,
            "title": source.title,
            "content": source.content,
        }
        for source in sorted(sources, key=lambda item: item.source_id)
    ]
    canonical_json = json.dumps(
        canonical_sources,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()

