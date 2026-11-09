import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.progress import Progress

from .client import DSBCClient
from .config import MANIFEST_PATH, RAW_CONTENT_DIR

logger = logging.getLogger("dsbc.scraper")


class DSBCScraper:
    """Scrapes raw HTML for all canon content pages listed in manifest.json."""

    def __init__(self, client: DSBCClient):
        self.client = client

    def load_manifest(self) -> List[Dict[str, Any]]:
        if not MANIFEST_PATH.exists():
            raise FileNotFoundError(
                f"Manifest not found at {MANIFEST_PATH}. Run 'dsbc index' first."
            )
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    async def scrape_content_page(
        self,
        book_id: int,
        content_id: int,
        url: str,
        force: bool = False,
    ) -> bool:
        cache_path = RAW_CONTENT_DIR / f"{book_id}_{content_id}.html"
        try:
            await self.client.fetch(url, cache_path=cache_path, force=force)
            return True
        except Exception as e:
            logger.error(f"Error scraping content {book_id}/{content_id} from {url}: {e}")
            return False

    async def scrape_all(
        self,
        script_filter: str = "all",
        book_id_filter: Optional[int] = None,
        limit: Optional[int] = None,
        force: bool = False,
        progress: Optional[Progress] = None,
    ) -> Dict[str, int]:
        books = self.load_manifest()

        if script_filter != "all":
            books = [b for b in books if b.get("script") == script_filter]

        if book_id_filter is not None:
            books = [b for b in books if b.get("book_id") == book_id_filter]

        # Flatten into list of items to scrape
        items_to_scrape = []
        for b in books:
            b_id = b.get("book_id")
            for ch in b.get("chapters", []):
                c_id = ch.get("content_id")
                url = ch.get("url")
                if b_id and c_id and url:
                    items_to_scrape.append((b_id, c_id, url))

        if limit:
            items_to_scrape = items_to_scrape[:limit]

        task_id = None
        if progress:
            task_id = progress.add_task(
                f"[green]Scraping {len(items_to_scrape)} content pages...",
                total=len(items_to_scrape),
            )

        success_count = 0
        failure_count = 0

        async def worker(item):
            nonlocal success_count, failure_count
            b_id, c_id, url = item
            ok = await self.scrape_content_page(b_id, c_id, url, force=force)
            if ok:
                success_count += 1
            else:
                failure_count += 1
            if progress and task_id is not None:
                progress.advance(task_id)

        await asyncio.gather(*(worker(item) for item in items_to_scrape))

        return {
            "total": len(items_to_scrape),
            "success": success_count,
            "failed": failure_count,
        }
