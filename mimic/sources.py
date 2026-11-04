"""Extension point for lawful catalog search. No platform scraping or download bypass."""
from typing import Protocol
import json
from pathlib import Path


class SourceAdapter(Protocol):
    def search(self, query: str) -> list[dict]: ...


class LicensedCatalog:
    """User-owned catalog: title, description, page_url, license. Links only."""
    def __init__(self, path: Path):
        self.path = path

    def search(self, query):
        if not self.path.exists():
            return []
        entries = json.loads(self.path.read_text())
        return [x for x in entries if x.get('license') and
                str(x.get('page_url','')).startswith('https://') and
                all(w in (x.get('title','')+' '+x.get('description','')).lower()
                    for w in query.lower().split())][:30]
