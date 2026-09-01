"""Render the single controlled agreement template."""

from __future__ import annotations

from pathlib import Path

from jinja2 import FileSystemLoader, StrictUndefined, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from claimgate.application.models import DraftDocument


class AgreementRenderer:
    template_name = "agreement.html.j2"

    def __init__(self, template_directory: Path | None = None) -> None:
        directory = template_directory or Path(__file__).parents[1] / "templates"
        self._environment = SandboxedEnvironment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
            undefined=StrictUndefined,
        )

    def render(self, draft: DraftDocument) -> str:
        template = self._environment.get_template(self.template_name)
        return template.render(draft=draft)

