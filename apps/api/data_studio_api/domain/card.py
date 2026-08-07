import json
from dataclasses import dataclass
from typing import Any

import bleach
import markdown
import yaml

from ..errors import ValidationError

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "article",
    "blockquote",
    "br",
    "code",
    "del",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "p",
    "pre",
    "span",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
}
_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
}


@dataclass(frozen=True)
class DatasetCard:
    metadata: dict[str, Any]
    markdown: str
    html: str


def parse_dataset_card(content: bytes) -> DatasetCard:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("invalid_card_encoding", "README.md must be UTF-8 encoded.") from exc

    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            raise ValidationError("invalid_card_yaml", "Malformed Dataset Card front matter.")
        end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
        if end is None:
            raise ValidationError("invalid_card_yaml", "Dataset Card front matter is not closed.")
        yaml_text = "".join(lines[1:end])
        body = "".join(lines[end + 1 :]).lstrip("\r\n")
        try:
            loaded = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as exc:
            raise ValidationError("invalid_card_yaml", f"Invalid Dataset Card YAML: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValidationError(
                "invalid_card_yaml", "Dataset Card metadata must be a YAML mapping."
            )
        metadata = json.loads(json.dumps(loaded, ensure_ascii=False, default=str))

    rendered = markdown.markdown(body, extensions=["fenced_code", "tables", "sane_lists"])
    sanitized = bleach.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return DatasetCard(metadata=metadata, markdown=body, html=sanitized)
