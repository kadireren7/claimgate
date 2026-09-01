"""Human-readable rendering of the authoritative canonical JSON receipt."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from claimgate.application.workflow import PdfDocumentAdapter
from claimgate.audit.models import DecisionReceipt

TEMPLATE_DIRECTORY = Path(__file__).parents[1] / "templates"


class DecisionReceiptRenderer:
    def __init__(self, template_directory: Path | None = None) -> None:
        directory = template_directory or TEMPLATE_DIRECTORY
        environment = Environment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(enabled_extensions=("html", "j2")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._template = environment.get_template("decision_receipt.html.j2")

    def render(self, receipt: DecisionReceipt) -> str:
        return self._template.render(receipt=receipt)


PdfAdapterFactory = Callable[[], PdfDocumentAdapter]


class DecisionReceiptPdfGenerator:
    """Uses the existing Foxit-compatible PDF adapter; JSON remains authoritative."""

    def __init__(
        self,
        adapter_factory: PdfAdapterFactory,
        renderer: DecisionReceiptRenderer | None = None,
    ) -> None:
        self._adapter_factory = adapter_factory
        self._renderer = renderer or DecisionReceiptRenderer()

    async def generate(self, receipt: DecisionReceipt, output_path: Path) -> Path:
        html = self._renderer.render(receipt)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return await self._adapter_factory().generate_pdf_from_html(html, output_path)
