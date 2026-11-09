import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .client import DSBCClient
from .config import (
    DEVANAGARI_LIST_URL,
    MANIFEST_PATH,
    RAW_BOOKS_DIR,
    RAW_DIR,
    ROMANIZED_LIST_URL,
)
from .parser import parse_book_page, parse_master_list

logger = logging.getLogger("dsbc.indexer")


class DSBCIndexer:
    """Builds a deterministic manifest of all texts, categories, and chapters in the DSBC canon."""

    def __init__(self, client: DSBCClient):
        self.client = client

    async def fetch_master_lists(self, script_filter: str = "all") -> List[Dict[str, Any]]:
        """Fetch and parse top-level book lists for Romanized and Devanagari."""
        books = []

        if script_filter in {"all", "romanized"}:
            cache_path = RAW_DIR / "browse_by_list_romanized.html"
            html = await self.client.fetch(ROMANIZED_LIST_URL, cache_path=cache_path)
            rom_books = parse_master_list(html, script_name="romanized")
            books.extend(rom_books)

        if script_filter in {"all", "devanagari"}:
            cache_path = RAW_DIR / "browse_by_list_devanagari.html"
            html = await self.client.fetch(DEVANAGARI_LIST_URL, cache_path=cache_path)
            dev_books = parse_master_list(html, script_name="devanagari")
            books.extend(dev_books)

        return books

    async def index_book(self, book_info: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """Fetch book page and enrich with bibliography and chapter list."""
        book_id = book_info.get("book_id")
        book_url = book_info.get("book_url")

        if not book_id or not book_url:
            return {**book_info, "bibliography": {}, "chapters": []}

        cache_path = RAW_BOOKS_DIR / f"{book_id}.html"
        try:
            html = await self.client.fetch(book_url, cache_path=cache_path, force=force)
            details = parse_book_page(html)
            return {
                **book_info,
                "title": details.get("title") or book_info.get("title", ""),
                "bibliography": details.get("bibliography", {}),
                "chapters": details.get("chapters", []),
            }
        except Exception as e:
            logger.error(f"Failed to index book {book_id}: {e}")
            return {
                **book_info,
                "bibliography": {},
                "chapters": [],
                "error": str(e),
            }

    async def build_manifest(
        self,
        script_filter: str = "all",
        limit: Optional[int] = None,
        force: bool = False,
        progress: Optional[Progress] = None,
    ) -> List[Dict[str, Any]]:
        """Crawl the canon index and save to data/manifest.json."""
        books = await self.fetch_master_lists(script_filter=script_filter)
        if limit:
            books = books[:limit]

        task_id = None
        if progress:
            task_id = progress.add_task(
                f"[cyan]Indexing {len(books)} books...", total=len(books)
            )

        async def worker(book: Dict[str, Any]):
            res = await self.index_book(book, force=force)
            if progress and task_id is not None:
                progress.advance(task_id)
            return res

        enriched_books = await asyncio.gather(*(worker(b) for b in books))

        # Sort deterministically by script then book_id
        enriched_books.sort(key=lambda b: (b.get("script", ""), b.get("book_id", 0)))

        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(enriched_books, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return enriched_books
