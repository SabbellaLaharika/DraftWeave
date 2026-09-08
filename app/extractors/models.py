from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class ExtractedContent:
    content_type: str  # 'text', 'url', or 'pdf'
    source_identifier: str  # URL string or content SHA-256 hash
    raw_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.content_type not in ("text", "url", "pdf"):
            raise ValueError(f"Invalid content_type: {self.content_type}")
